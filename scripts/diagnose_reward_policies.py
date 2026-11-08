"""Compare deterministic and sampled PPO actions on the pilot validation split."""

from collections import Counter
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import torch
    from stable_baselines3 import PPO
    from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv

    torch.set_num_threads(1)
    out = ROOT / "results/figgie_competitiveness_20261106_pilot"
    results = {}
    for config_path in sorted((out / "configs").glob("*.yaml")):
        cfg = yaml.safe_load(config_path.read_text())
        model = PPO.load(
            ROOT / "artifacts" / cfg["run_name"] / "best_model/best_model.zip"
        )
        mode_results = {}
        for deterministic in (True, False):
            env = SimpleFiggieEnv(EnvConfig(**cfg["env"]))
            actions = Counter()
            profits = []
            for seed in range(1500000, 1500100):
                obs, _ = env.reset(seed=seed)
                done = False
                info = {}
                while not done:
                    action, _ = model.predict(obs, deterministic=deterministic)
                    actions[
                        env.describe_action(
                            int(action), env.num_suits, env.config.market_mode
                        )
                    ] += 1
                    obs, _, term, trunc, info = env.step(int(action))
                    done = term or trunc
                profits.append(info["final_bankroll"] - env.config.starting_cash)
            mode_results["deterministic" if deterministic else "stochastic"] = {
                "mean_profit": sum(profits) / len(profits),
                "action_counts": dict(actions),
                "top_action_fraction": max(actions.values()) / sum(actions.values()),
                "episodes": len(profits),
            }
            env.close()
        results[config_path.stem] = mode_results
        print(config_path.stem, mode_results, flush=True)
    (out / "deterministic_vs_stochastic_validation.json").write_text(
        json.dumps(results, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
