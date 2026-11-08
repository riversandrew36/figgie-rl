"""Collect teacher actions, behavior-clone each teacher, then fine-tune with PPO."""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
import yaml
from stable_baselines3 import PPO
from figgie_rl.agents.baselines import policy_for_difficulty
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.train.evaluate import run_evaluation
from figgie_rl.train.train_ppo import make_env

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/figgie_competitiveness_20261106_pilot/imitation"
CFG = yaml.safe_load((OUT / "config.yaml").read_text())
TEACHERS = ("bayesian", "hunter", "banker", "detective", "bluffer")


def collect(label, train):
    env = SimpleFiggieEnv(EnvConfig(**CFG["env"]))
    teacher = policy_for_difficulty(label)
    observations = []
    actions = []
    seeds = range(1503000, 1503025) if train else range(1503050, 1503060)
    for seed in seeds:
        obs, _ = env.reset(seed=seed)
        rng = np.random.default_rng(seed + 900000)
        done = False
        while not done:
            action = env.encode_semantic_action(
                teacher.act(env._opponent_view(env.agent_idx), rng)
            )
            observations.append(obs.copy())
            actions.append(action)
            obs, _, terminated, truncated, _ = env.step(action)
            done = terminated or truncated
    env.close()
    return np.asarray(observations), np.asarray(actions, dtype=np.int64)


def main():
    torch.set_num_threads(1)
    OUT.mkdir(parents=True, exist_ok=True)
    summaries = []
    for label in TEACHERS:
        data = OUT / label
        data.mkdir(exist_ok=True)
        obs, act = collect(label, True)
        valobs, valact = collect(label, False)
        env = make_env(CFG["env"], CFG["seed"])
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=CFG["train"]["learning_rate"],
            n_steps=256,
            batch_size=256,
            gamma=1.0,
            verbose=0,
            seed=CFG["seed"],
        )
        x = torch.as_tensor(obs, dtype=torch.float32, device=model.device)
        y = torch.as_tensor(act, dtype=torch.long, device=model.device)
        rng = np.random.default_rng(CFG["seed"])
        for _ in range(8):
            order = rng.permutation(len(y))
            for start in range(0, len(y), 256):
                batch = order[start : start + 256]
                dist = model.policy.get_distribution(x[batch]).distribution
                loss = F.cross_entropy(dist.logits, y[batch])
                model.policy.optimizer.zero_grad()
                loss.backward()
                model.policy.optimizer.step()
        with torch.no_grad():
            pred = (
                model.policy.get_distribution(
                    torch.as_tensor(valobs, dtype=torch.float32, device=model.device)
                )
                .distribution.probs.argmax(dim=1)
                .cpu()
                .numpy()
            )
        agreement = float((pred == valact).mean())
        bc = data / "bc.zip"
        model.save(bc)
        model.learn(
            total_timesteps=20480, reset_num_timesteps=False, progress_bar=False
        )
        ft = data / "bc_ppo.zip"
        model.save(ft)
        env.close()
        for phase, path in [("bc", bc), ("bc_ppo", ft)]:
            report = run_evaluation(
                model_path=str(path),
                config_path=str(OUT / "eval.yaml"),
                episodes=100,
                seed=1503100,
                benchmark=True,
            )
            (data / f"{phase}_evaluation.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            ppo = next(x for x in report["aggregates"] if x["policy"] == "PPO")
            summaries.append(
                {
                    "teacher": label,
                    "phase": phase,
                    "agreement": agreement,
                    "expert_transitions": len(act),
                    "ppo_steps": 0 if phase == "bc" else 20480,
                    "profit": ppo["mean_profit"],
                    "ci95": ppo["profit_ci95"],
                }
            )
        print(
            label, "agreement", round(agreement, 3), "transitions", len(act), flush=True
        )
    (OUT / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
