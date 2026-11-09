"""Bounded 2x2 study of feasible-action masks and conditional action heads."""

from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import torch
import yaml
from sb3_contrib import MaskablePPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.monitor import Monitor
from figgie_rl.agents.baselines import policy_for_difficulty
from figgie_rl.agents.structured_policy import StructuredMaskablePolicy
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.envs.action_interface import ActionInterface

ROOT = Path(__file__).resolve().parents[2]


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    temporary = p.with_suffix(p.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(p)


def load(p):
    return json.loads(Path(p).read_text())


def source_hashes(config):
    files = [
        Path(__file__),
        Path(config),
        ROOT / "docs/ACTION_INTERFACES.md",
        ROOT / "figgie_rl/envs/action_interface.py",
        ROOT / "figgie_rl/agents/structured_policy.py",
        ROOT / "figgie_rl/envs/simple_figgie_env.py",
        ROOT / "figgie_rl/envs/mechanics.py",
        ROOT / "figgie_rl/agents/styles.py",
        ROOT / "figgie_rl/agents/baselines.py",
    ]
    return {str(p.resolve()): digest(p) for p in files}


def make_env(spec, seed, lineup="familiar"):
    cfg = deepcopy(spec["env"])
    cfg.update(seed=seed, opponent_difficulties=spec["lineups"][lineup])
    return ActionInterface(SimpleFiggieEnv(EnvConfig(**cfg)))


def evaluate(spec, model, masked, seed, episodes, lineup="familiar", baseline=None):
    env = make_env(spec, seed, lineup)
    base = env.unwrapped
    actions = Counter()
    rows = []
    bad = 0
    steps = 0
    expert = None if baseline in (None, "hold") else policy_for_difficulty(baseline)
    for episode in range(episodes):
        obs, _ = env.reset(seed=seed + episode)
        rng = np.random.default_rng(seed + 500000 + episode)
        initial = base.initial_inventories[base.agent_idx].tolist()
        done = False
        while not done:
            mask = env.action_masks()
            if baseline == "hold":
                action = 0
            elif expert is not None:
                action = base.encode_semantic_action(
                    expert.act(base._opponent_view(base.agent_idx), rng)
                )
            else:
                action, _ = model.predict(
                    obs, deterministic=True, action_masks=mask if masked else None
                )
                action = int(action)
            bad += int(not mask[action])
            steps += 1
            actions[base.describe_action(action, 4, "endogenous")] += 1
            obs, _, term, trunc, info = env.step(action)
            done = term or trunc
        rows.append(
            {
                "episode": episode,
                "seed": seed + episode,
                "profit": info["final_bankroll"] - base.config.starting_cash,
                "bankroll": info["final_bankroll"],
                "win": info["winner_indices"] == [base.agent_idx],
                "rank": info["final_rank"],
                "trades": base.agent_trade_count,
                "quote_fills": base.agent_quote_fill_count,
                "inventory_risk": info["episode_metrics"]["inventory_risk"],
                "initial_inventory": initial,
                "goal_suit": int(info["goal_suit_idx"]),
            }
        )
    env.close()
    profits = [r["profit"] for r in rows]
    return {
        "lineup": lineup,
        "seed": seed,
        "episodes": episodes,
        "evaluation_split": "development",
        "policy": baseline or "learner",
        "use_masking": masked if baseline is None else False,
        "mean_profit": float(np.mean(profits)),
        "profit_ci95": float(1.96 * np.std(profits) / np.sqrt(episodes)),
        "win_rate": sum(r["win"] for r in rows) / episodes,
        "mean_rank": float(np.mean([r["rank"] for r in rows])),
        "mean_trades": float(np.mean([r["trades"] for r in rows])),
        "infeasible_fraction": bad / steps,
        "top_action_fraction": max(actions.values()) / steps,
        "action_counts": dict(actions),
        "per_episode": rows,
    }


def train(spec, out, condition, seed):
    folder = out / "runs" / f"{condition}_{seed}"
    marker = folder / "selected.json"
    if marker.exists():
        return
    if folder.exists():
        raise RuntimeError(
            f"Partial run preserved at {folder}; inspect before restarting"
        )
    folder.mkdir(parents=True)
    masked = condition.endswith("_masked")
    structured = condition.startswith("structured")
    model = None
    choices = []
    for stage in range(spec["stages"]):
        vec = DummyVecEnv(
            [
                lambda rank=r: Monitor(make_env(spec, seed + stage * 1000 + rank))
                for r in range(spec["train"]["n_envs"])
            ]
        )
        if model is None:
            settings = {k: v for k, v in spec["train"].items() if k != "n_envs"}
            model = MaskablePPO(
                StructuredMaskablePolicy if structured else "MlpPolicy",
                vec,
                seed=seed,
                device="cpu",
                verbose=0,
                **settings,
            )
        else:
            model.set_env(vec)
        model.learn(
            total_timesteps=spec["chunk_timesteps"],
            reset_num_timesteps=False,
            use_masking=masked,
        )
        path = folder / f"stage_{stage:02d}.zip"
        model.save(path)
        report = evaluate(
            spec,
            model,
            masked,
            spec["validation"]["seed"],
            spec["validation"]["episodes"],
        )
        report["evaluation_split"] = "validation"
        save(folder / f"validation_{stage:02d}.json", report)
        choices.append(
            {
                "model": str(path),
                "sha256": digest(path),
                "stage": stage,
                "timesteps": model.num_timesteps,
                "mean_profit": report["mean_profit"],
                "win_rate": report["win_rate"],
                "mean_rank": report["mean_rank"],
            }
        )
        save(
            path.with_suffix(".metadata.json"),
            {
                "algorithm": "MaskablePPO",
                "condition": condition,
                "use_masking": masked,
                "structured": structured,
                "seed": seed,
                "stage": stage,
                "specification": spec,
                "parameter_count": sum(p.numel() for p in model.policy.parameters()),
                "action_schema": "legacy_endogenous_105",
                "policy_class": type(model.policy).__name__,
                "command": sys.argv,
            },
        )
        vec.close()
        print(
            condition,
            seed,
            "stage",
            stage + 1,
            "profit",
            round(report["mean_profit"], 2),
            flush=True,
        )
    choice = max(
        choices, key=lambda r: (r["mean_profit"], r["win_rate"], -r["mean_rank"])
    )
    choice.update(
        condition=condition,
        seed=seed,
        use_masking=masked,
        parameter_count=sum(p.numel() for p in model.policy.parameters()),
    )
    save(marker, choice)


def benchmark(spec, out, condition, seed):
    frozen = load(out / "frozen_selection.json")
    choice = frozen["models"][f"{condition}_{seed}"]
    assert digest(choice["model"]) == choice["sha256"]
    model = MaskablePPO.load(choice["model"], device="cpu")
    for lineup in spec["lineups"]:
        target = out / "exploratory" / f"{condition}_{seed}_{lineup}.json"
        if target.exists():
            continue
        report = evaluate(
            spec,
            model,
            choice["use_masking"],
            spec["exploratory"]["seed"],
            spec["exploratory"]["episodes"],
            lineup,
        )
        report["evaluation_split"] = spec.get("benchmark_split", "exploratory")
        save(target, report)
    print("evaluated", condition, seed, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/action_interfaces.yaml")
    parser.add_argument("--job", choices=["train", "benchmark"])
    parser.add_argument(
        "--condition",
        choices=["flat", "flat_masked", "structured", "structured_masked"],
    )
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    torch.set_num_threads(1)
    config = Path(args.config).resolve()
    spec = yaml.safe_load(config.read_text())
    out = ROOT / "results" / spec["study_id"]
    fingerprints = source_hashes(config)
    if args.job:
        assert load(out / "manifest.json")["source_hashes"] == fingerprints
        if args.job == "train":
            train(spec, out, args.condition, args.seed)
        else:
            benchmark(spec, out, args.condition, args.seed)
        return
    manifest = out / "manifest.json"
    if manifest.exists():
        assert load(manifest)["source_hashes"] == fingerprints, (
            "Study source changed; use a new study ID"
        )
    else:
        out.mkdir(parents=True, exist_ok=True)
        save(
            manifest,
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_hashes": fingerprints,
                "specification": spec,
                "dependencies": {
                    p: version(p)
                    for p in [
                        "stable-baselines3",
                        "sb3-contrib",
                        "torch",
                        "numpy",
                        "gymnasium",
                    ]
                },
                "source_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "compute": {
                    "workers": spec["workers"],
                    "threads_per_worker": 1,
                    "training_steps": len(spec["conditions"])
                    * len(spec["seeds"])
                    * spec["stages"]
                    * spec["chunk_timesteps"],
                },
            },
        )
        shutil.copyfile(config, out / "config.yaml")
    jobs = [(c, s) for c in spec["conditions"] for s in spec["seeds"]]

    def worker(job, phase):
        (out / "logs").mkdir(exist_ok=True)
        with (out / "logs" / f"{job[0]}_{job[1]}_{phase}.log").open("w") as log:
            env = dict(
                os.environ,
                PYTHONPATH=str(ROOT),
                OMP_NUM_THREADS="1",
                MKL_NUM_THREADS="1",
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "figgie_rl.train.action_study",
                    "--config",
                    str(config),
                    "--job",
                    phase,
                    "--condition",
                    job[0],
                    "--seed",
                    str(job[1]),
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )

    with ThreadPoolExecutor(max_workers=spec["workers"]) as pool:
        list(pool.map(lambda job: worker(job, "train"), jobs))
    choices = {
        f"{c}_{s}": load(out / "runs" / f"{c}_{s}" / "selected.json") for c, s in jobs
    }
    frozen = out / "frozen_selection.json"
    if not frozen.exists():
        save(
            frozen,
            {
                "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_hashes": fingerprints,
                "models": choices,
            },
        )
    else:
        assert load(frozen)["models"] == choices
    for lineup in spec["lineups"]:
        for label in ("hold", "bayesian"):
            target = out / "exploratory" / f"{label}_{lineup}.json"
            if not target.exists():
                save(
                    target,
                    evaluate(
                        spec,
                        None,
                        False,
                        spec["exploratory"]["seed"],
                        spec["exploratory"]["episodes"],
                        lineup,
                        baseline=label,
                    ),
                )
    with ThreadPoolExecutor(max_workers=spec["workers"]) as pool:
        list(pool.map(lambda job: worker(job, "benchmark"), jobs))
    print(
        f"All {len(spec['conditions'])} action-interface conditions completed on {len(spec['seeds'])} seeds.",
        flush=True,
    )


if __name__ == "__main__":
    main()
