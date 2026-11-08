"""Describe selected policies' actions on exploratory seeds; never selects models."""
from __future__ import annotations

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
    spec = yaml.safe_load((ROOT / "configs/rl_study.yaml").read_text())
    out = ROOT / "results" / spec["study_id"]
    frozen = json.loads((out / "frozen_selection.json").read_text())
    diagnostics = {}
    for arm in ("fixed", "self_play"):
        for training_seed in spec["training_seeds"]:
            name = f"{arm}_seed_{training_seed}"
            cfg = yaml.safe_load((out / "configs" / f"{name}.yaml").read_text())
            model = PPO.load(frozen["models"][name]["model"])
            env = SimpleFiggieEnv(EnvConfig(**cfg["env"]))
            actions = Counter()
            action_details = Counter()
            trades, quote_fills = [], []
            total_returns, discounted_returns, final_profits = [], [], []
            first_trace = []
            for seed in range(spec["exploratory"]["seed"], spec["exploratory"]["seed"] + 50):
                obs, _ = env.reset(seed=seed)
                done = False
                initial_value = env._mark_to_market(env.agent_idx)
                undiscounted, discounted, tick = 0.0, 0.0, 0
                trace = [{"step": 0, "marked_wealth": initial_value, "cash": float(env.cash[env.agent_idx])}]
                while not done:
                    action, _ = model.predict(obs, deterministic=True)
                    semantic = env.decode_discrete_action(int(action), env.num_suits, market_mode=env.config.market_mode)
                    actions[semantic.kind] += 1
                    action_details[env.describe_action(int(action), env.num_suits, env.config.market_mode)] += 1
                    obs, reward, terminated, truncated, info = env.step(int(action))
                    undiscounted += float(reward)
                    discounted += cfg["train"]["gamma"]**tick * float(reward)
                    tick += 1
                    done = terminated or truncated
                    trace.append({"step": tick,
                                  "marked_wealth": float(info["final_bankroll"] if done else info["mark_to_market"]),
                                  "cash": float(env.cash[env.agent_idx])})
                assert abs(undiscounted - (info["final_bankroll"]-initial_value)) < 1e-6
                total_returns.append(undiscounted)
                discounted_returns.append(discounted)
                final_profits.append(info["final_bankroll"]-env.config.starting_cash)
                if not first_trace:
                    first_trace = trace
                trades.append(env.agent_trade_count)
                quote_fills.append(env.agent_quote_fill_count)
            total = sum(actions.values())
            diagnostics[name] = {"episodes": 50, "seed_start": spec["exploratory"]["seed"],
                                 "evaluation_split": "exploratory_diagnostic",
                                 "mean_undiscounted_return": sum(total_returns)/len(total_returns),
                                 "mean_discounted_return": sum(discounted_returns)/len(discounted_returns),
                                 "mean_final_profit": sum(final_profits)/len(final_profits),
                                 "gamma": cfg["train"]["gamma"],
                                 "first_episode_trace": first_trace,
                                 "action_counts": dict(actions),
                                 "action_details": dict(action_details),
                                 "action_fractions": {k: v/total for k,v in actions.items()},
                                 "mean_executed_trades": sum(trades)/len(trades),
                                 "mean_quote_fills": sum(quote_fills)/len(quote_fills)}
            env.close()
            print(name, diagnostics[name], flush=True)
    (out / "action_diagnostics.json").write_text(json.dumps(diagnostics, indent=2) + "\n")


if __name__ == "__main__":
    main()
