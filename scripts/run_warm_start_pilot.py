"""Development pilot: imitate a scripted teacher, then fine-tune with masked PPO."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from pathlib import Path

import numpy as np
import torch
import yaml
from sb3_contrib import MaskablePPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from figgie_rl.envs.simple_figgie_env import EnvConfig
from figgie_rl.train.action_study import evaluate, make_env, save
from figgie_rl.train.warm_start import (
    collect_demonstrations,
    imitation_agreement,
    pretrain,
)

ROOT = Path(__file__).resolve().parents[1]
T_975 = {2: 4.302653, 3: 3.182446, 4: 2.776445}


def vec_env(spec, seed):
    lineups = spec.get("train_lineups", ["familiar"])
    return DummyVecEnv(
        [
            lambda rank=rank: Monitor(make_env(spec, seed + rank, lineups[rank % len(lineups)]))
            for rank in range(spec["train"]["n_envs"])
        ]
    )


def run(job):
    spec, teacher, seed = job
    torch.set_num_threads(1)
    folder = ROOT / "results" / spec["study_id"] / "runs" / f"{teacher}_{seed}"
    folder.mkdir(parents=True, exist_ok=False)
    env_values = deepcopy(spec["env"]) | {
        "opponent_difficulties": spec["lineups"]["familiar"]
    }
    config = EnvConfig(**env_values)
    demo = spec["demonstrations"]
    train_data = collect_demonstrations(
        config, teacher, demo["train_seed"] + seed * 10_000, demo["train_episodes"]
    )
    held_out = collect_demonstrations(
        config, teacher, demo["holdout_seed"], demo["holdout_episodes"]
    )
    settings = {k: v for k, v in spec["train"].items() if k != "n_envs"}
    model = MaskablePPO(
        "MlpPolicy",
        vec_env(spec, seed),
        seed=seed,
        device="cpu",
        verbose=0,
        policy_kwargs={"net_arch": spec["net_arch"]},
        **settings,
    )
    losses = pretrain(model, train_data, epochs=demo["epochs"], seed=seed)
    summary = {
        "teacher": teacher,
        "seed": seed,
        "demonstration_samples": len(train_data.actions),
        "dropped_infeasible": train_data.dropped_infeasible,
        "teacher_demo_profit": train_data.mean_profit,
        "agreement_train": imitation_agreement(model, train_data),
        "agreement_holdout": imitation_agreement(model, held_out),
        **losses,
    }
    candidates = []

    def checkpoint(stage):
        path = folder / f"stage_{stage:02d}.zip"
        model.save(path)
        report = evaluate(
            spec, model, True, spec["validation"]["seed"], spec["validation"]["episodes"]
        )
        candidates.append(
            {"stage": stage, "model": str(path), "profit": report["mean_profit"]}
        )
        print(teacher, seed, "stage", stage, round(report["mean_profit"], 2), flush=True)

    checkpoint(0)
    for stage in range(1, spec["stages"] + 1):
        model.set_env(vec_env(spec, seed + stage * 1000))
        model.learn(
            total_timesteps=spec["chunk_timesteps"],
            reset_num_timesteps=False,
            use_masking=True,
        )
        checkpoint(stage)
    choice = max(candidates, key=lambda row: row["profit"])
    summary |= {"validation": candidates, "selected_stage": choice["stage"]}
    selected = MaskablePPO.load(choice["model"], device="cpu")
    final = MaskablePPO.load(candidates[-1]["model"], device="cpu")
    imitation = MaskablePPO.load(candidates[0]["model"], device="cpu")
    results = {}
    for label, policy in (("imitation", imitation), ("final", final), ("selected", selected)):
        for lineup in spec["lineups"]:
            results[f"{label}_{lineup}"] = [
                row["profit"]
                for row in evaluate(
                    spec,
                    policy,
                    True,
                    spec["exploratory"]["seed"],
                    spec["exploratory"]["episodes"],
                    lineup,
                )["per_episode"]
            ]
    summary["profits"] = results
    save(folder / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/warm_start_pilot.yaml")
    args = parser.parse_args()
    spec = yaml.safe_load(Path(args.config).read_text())
    out = ROOT / "results" / spec["study_id"]
    if out.exists():
        raise RuntimeError(f"{out} exists; use a new study_id")
    out.mkdir(parents=True)
    jobs = [(spec, teacher, seed) for teacher in spec["teachers"] for seed in spec["seeds"]]
    with ProcessPoolExecutor(spec["workers"]) as pool:
        runs = list(pool.map(run, jobs))
    baselines = {
        lineup: {
            name: np.array(
                [
                    row["profit"]
                    for row in evaluate(
                        spec,
                        None,
                        False,
                        spec["exploratory"]["seed"],
                        spec["exploratory"]["episodes"],
                        lineup,
                        baseline=name,
                    )["per_episode"]
                ]
            )
            for name in ("hold", "bayesian", "hunter", "bluffer")
        }
        for lineup in spec["lineups"]
    }
    save(out / "baselines.json", {k: {n: v.tolist() for n, v in b.items()} for k, b in baselines.items()})
    for lineup, values in baselines.items():
        print(lineup, {name: round(float(v.mean()), 2) for name, v in values.items()})
    for run_summary in runs:
        print(
            run_summary["teacher"],
            run_summary["seed"],
            "agreement",
            round(run_summary["agreement_holdout"], 3),
            "dropped",
            run_summary["dropped_infeasible"],
            "selected stage",
            run_summary["selected_stage"],
            "validation",
            [round(row["profit"], 1) for row in run_summary["validation"]],
        )
    for teacher in spec["teachers"]:
        group = [r for r in runs if r["teacher"] == teacher]
        for label in ("imitation", "final", "selected"):
            for lineup, base in baselines.items():
                profits = [np.array(r["profits"][f"{label}_{lineup}"]) for r in group]
                means = [float(p.mean()) for p in profits]
                text = f"{teacher:8} {label:9} {lineup:8} profit {np.mean(means):7.2f}"
                for name, reference in base.items():
                    edges = [float((p - reference).mean()) for p in profits]
                    half = T_975[len(edges) - 1] * np.std(edges, ddof=1) / np.sqrt(len(edges))
                    text += f" | -{name} {np.mean(edges):+.2f}±{half:.2f}"
                if label != "imitation":
                    gains = [
                        float(
                            (
                                np.array(r["profits"][f"{label}_{lineup}"])
                                - np.array(r["profits"][f"imitation_{lineup}"])
                            ).mean()
                        )
                        for r in group
                    ]
                    half = T_975[len(gains) - 1] * np.std(gains, ddof=1) / np.sqrt(len(gains))
                    text += f" | RL gain {np.mean(gains):+.2f}±{half:.2f}"
                print(text)


if __name__ == "__main__":
    main()
