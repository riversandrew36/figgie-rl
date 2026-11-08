"""Compare greedy and sampled policies on the predeclared validation episodes."""

from collections import Counter
import json
from pathlib import Path
import sys
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import torch
    from stable_baselines3 import PPO
    from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv

    torch.set_num_threads(1)
    spec = yaml.safe_load((ROOT / "configs/competitiveness_main.yaml").read_text())
    out = ROOT / "results" / spec["study_id"]
    details = {}
    for arm in ("fixed", "self_play"):
        for seed in spec["training_seeds"]:
            key = f"{arm}_seed_{seed}"
            choice = json.loads((out / "selection" / f"{key}.json").read_text())
            cfg = yaml.safe_load((out / "configs" / f"{key}.yaml").read_text())
            modes = {}
            for deterministic in (True, False):
                np.random.seed(
                    spec["validation"]["seed"] + seed + (0 if deterministic else 50000)
                )
                torch.manual_seed(seed + (0 if deterministic else 50000))
                model = PPO.load(choice["model"])
                env = SimpleFiggieEnv(EnvConfig(**cfg["env"]))
                actions = Counter()
                profits = []
                fills = []
                for ep in range(spec["validation"]["episodes"]):
                    obs, _ = env.reset(seed=spec["validation"]["seed"] + ep)
                    done = False
                    while not done:
                        act, _ = model.predict(obs, deterministic=deterministic)
                        actions[
                            env.describe_action(
                                int(act), env.num_suits, env.config.market_mode
                            )
                        ] += 1
                        obs, _, term, trunc, info = env.step(int(act))
                        done = term or trunc
                    profits.append(info["final_bankroll"] - env.config.starting_cash)
                    fills.append(info["agent_quote_fill_rate"])
                modes["deterministic" if deterministic else "stochastic"] = {
                    "mean_profit": float(np.mean(profits)),
                    "profit_sd": float(np.std(profits, ddof=1)),
                    "mean_quote_fill_rate": float(np.mean(fills)),
                    "action_counts": dict(actions),
                    "top_action_fraction": max(actions.values())
                    / sum(actions.values()),
                    "episodes": len(profits),
                }
                env.close()
            details[key] = modes
            print(key, modes, flush=True)
    (out / "policy_modes_validation.json").write_text(
        json.dumps(details, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
