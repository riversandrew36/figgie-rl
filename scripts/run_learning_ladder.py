"""Train one rung of the Figgie learning ladder and save its learning curve."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from copy import deepcopy
from pathlib import Path

import numpy as np
import torch
import yaml
from sb3_contrib import MaskablePPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from figgie_rl.train.action_study import evaluate, make_env, save

ROOT = Path(__file__).resolve().parents[1]
LINEUP = "ladder"


def step_spec(spec: dict, step: dict) -> dict:
    """Resolve one rung into the form used by the shared evaluator."""
    resolved = deepcopy(spec)
    resolved["env"] |= {
        "include_goal_oracle_features": step["goal_shown"],
        "include_goal_belief_features": step["goal_odds"],
    }
    resolved["lineups"] = {LINEUP: spec["lineups"][step["lineup"]]}
    return resolved


def train_seed(job: tuple[dict, dict, int]) -> list[dict]:
    spec, step, seed = job
    torch.set_num_threads(1)
    settings = {key: value for key, value in spec["train"].items() if key != "n_envs"}
    trial = spec["evaluation"]

    def vec(offset: int) -> DummyVecEnv:
        return DummyVecEnv(
            [
                lambda rank=rank: Monitor(make_env(spec, seed + offset + rank, LINEUP))
                for rank in range(spec["train"]["n_envs"])
            ]
        )

    model = MaskablePPO("MlpPolicy", vec(0), seed=seed, device="cpu", verbose=0, **settings)
    rows = []
    for stage in range(spec["stages"] + 1):
        if stage:
            model.set_env(vec(stage * 1000))
            model.learn(
                total_timesteps=spec["chunk_timesteps"],
                reset_num_timesteps=False,
                use_masking=True,
            )
        report = evaluate(spec, model, True, trial["seed"], trial["episodes"], LINEUP)
        rows.append(
            {
                "step": step["number"],
                "seed": seed,
                "timesteps": stage * spec["chunk_timesteps"],
                "mean_profit": report["mean_profit"],
                "win_rate": report["win_rate"],
                "mean_trades": report["mean_trades"],
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/learning_ladder.yaml")
    parser.add_argument("--step", type=int, required=True)
    args = parser.parse_args()
    raw = yaml.safe_load(Path(args.config).read_text())
    step = next(item for item in raw["steps"] if item["number"] == args.step)
    spec = step_spec(raw, step)
    out = ROOT / "results" / raw["study_id"] / f"step_{step['number']}_{step['name']}"
    if out.exists():
        raise RuntimeError(f"{out} exists; move it or use a new study_id")
    out.mkdir(parents=True)
    jobs = [(spec, step, seed) for seed in raw["seeds"]]
    with ProcessPoolExecutor(raw["workers"]) as pool:
        rows = [row for result in pool.map(train_seed, jobs) for row in result]
    with (out / "curve.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    trial = spec["evaluation"]
    hold = evaluate(
        spec, None, False, trial["seed"], trial["episodes"], LINEUP, baseline="hold"
    )["mean_profit"]
    save(out / "summary.json", {"step": step, "hold_profit": hold, "curve": rows})
    print(f"Step {step['number']} ({step['name']}), Hold {hold:.2f}")
    for timesteps in sorted({row["timesteps"] for row in rows}):
        group = [row for row in rows if row["timesteps"] == timesteps]
        print(
            f"  {timesteps:>7} steps: profit "
            f"{np.mean([row['mean_profit'] for row in group]):8.2f} "
            f"trades {np.mean([row['mean_trades'] for row in group]):6.1f} "
            f"by seed {[round(row['mean_profit'], 1) for row in group]}"
        )


if __name__ == "__main__":
    main()
