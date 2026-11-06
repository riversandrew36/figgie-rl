"""Does "buy the most likely goal suit at any price" still print money?

The exogenous market sells every suit near $5 and will force a random holder
to trade. The endogenous market does neither. This script measures that
difference. It is a game-design diagnostic, not an agent result: its seeds
start at 900_000 and must not be reused as the untouched test range.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

import numpy as np

from figgie_rl.agents.baselines import (
    BayesianGoalTrader,
    BaselinePolicy,
    NaiveGoalBuyer,
    policies_from_difficulties,
)
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv

DIAGNOSTIC_SEED = 900_000
ARMS: tuple[dict[str, Any], ...] = (
    {
        "name": "exogenous_outside_book",
        "market_mode": "exogenous",
        "opponents": ("weak", "average", "tough"),
    },
    {
        "name": "endogenous_legacy_quoters",
        "market_mode": "endogenous",
        "opponents": ("weak", "average", "tough"),
    },
    {
        "name": "endogenous_reservation_quoters",
        "market_mode": "endogenous",
        "opponents": ("reservation", "reservation", "reservation"),
    },
    {
        "name": "endogenous_style_quoters",
        "market_mode": "endogenous",
        "opponents": ("hunter", "banker", "detective"),
    },
    {
        "name": "endogenous_style_quoters_with_bluffer",
        "market_mode": "endogenous",
        "opponents": ("banker", "detective", "bluffer"),
    },
)
POLICIES: dict[str, BaselinePolicy | None] = {
    "Hold": None,
    "Naive goal buyer": NaiveGoalBuyer(),
    "Bayesian": BayesianGoalTrader(),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Goal-buying diagnostic for both market modes.")
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--seed", type=int, default=DIAGNOSTIC_SEED)
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional JSON path. The same summary is printed either way.",
    )
    return parser.parse_args()


def _summarize(profits: list[float], trades: list[int]) -> dict[str, float | int]:
    count = len(profits)
    return {
        "episodes": count,
        "mean_profit": statistics.fmean(profits),
        "profit_ci95": 1.96 * statistics.pstdev(profits) / (count ** 0.5),
        "mean_trades": statistics.fmean(trades),
    }


def _paired(left: list[float], right: list[float]) -> dict[str, float]:
    differences = [a - b for a, b in zip(left, right)]
    scale = statistics.stdev(differences) / (len(differences) ** 0.5)
    return {
        "mean_difference": statistics.fmean(differences),
        "ci95": 1.96 * scale,
    }


def _run_policy(
    *,
    market_mode: str,
    opponents: tuple[str, ...],
    policy: BaselinePolicy | None,
    episodes: int,
    seed: int,
) -> tuple[list[float], list[int]]:
    env = SimpleFiggieEnv(
        config=EnvConfig(
            market_mode=market_mode,
            max_steps=120,
            pot_conserving_settlement=True,
            opponent_difficulties=opponents,
            include_belief_features=False,
            include_goal_belief_features=False,
        ),
        opponent_policies=policies_from_difficulties(opponents),
    )
    profits: list[float] = []
    trades: list[int] = []
    for episode in range(episodes):
        _, _ = env.reset(seed=seed + episode)
        done = False
        info: dict[str, Any] = {}
        rng = np.random.default_rng(seed + 100_000 + episode)
        while not done:
            if policy is None:
                action = 0
            else:
                view = env._opponent_view(env.agent_idx)
                action = env.encode_semantic_action(policy.act(view, rng))
            _, _, terminated, truncated, info = env.step(action)
            done = terminated or truncated
        profits.append(float(info["final_bankroll"]) - float(env.config.starting_cash))
        trades.append(int(info["agent_trade_count"]))
    env.close()
    return profits, trades


def run_diagnostic(episodes: int, seed: int) -> dict[str, Any]:
    if episodes < 2:
        raise ValueError("episodes must be >= 2 so a paired interval is defined")
    report: dict[str, Any] = {
        "episodes": episodes,
        "base_seed": seed,
        "seed_note": (
            "Diagnostic seeds only. Do not reuse this range as the agent test set."
        ),
        "profit_definition": "final_bankroll - starting_cash",
        "ci_method": "1.96 * population_stdev / sqrt(n); paired uses sample stdev",
        "arms": [],
    }
    for arm in ARMS:
        policy_rows: dict[str, Any] = {}
        stored: dict[str, list[float]] = {}
        for name, policy in POLICIES.items():
            profits, trades = _run_policy(
                market_mode=str(arm["market_mode"]),
                opponents=tuple(arm["opponents"]),
                policy=policy,
                episodes=episodes,
                seed=seed,
            )
            stored[name] = profits
            policy_rows[name] = _summarize(profits, trades)
        report["arms"].append(
            {
                "name": arm["name"],
                "market_mode": arm["market_mode"],
                "opponents": list(arm["opponents"]),
                "policies": policy_rows,
                "naive_minus_bayesian": _paired(stored["Naive goal buyer"], stored["Bayesian"]),
                "naive_minus_hold": _paired(stored["Naive goal buyer"], stored["Hold"]),
            }
        )
    return report


def print_report(report: dict[str, Any]) -> None:
    print(
        f"Goal-buy diagnostic, {report['episodes']} shared seeds "
        f"starting at {report['base_seed']}."
    )
    for arm in report["arms"]:
        print(f"\n{arm['name']}  opponents={arm['opponents']}")
        for name, row in arm["policies"].items():
            print(
                f"  {name:>18}  profit={row['mean_profit']:8.2f} ± {row['profit_ci95']:6.2f}"
                f"   trades={row['mean_trades']:.1f}"
            )
        paired = arm["naive_minus_bayesian"]
        versus_hold = arm["naive_minus_hold"]
        print(
            "  naive - bayesian"
            f"  {paired['mean_difference']:8.2f} ± {paired['ci95']:6.2f}"
        )
        print(
            "  naive - hold    "
            f"  {versus_hold['mean_difference']:8.2f} ± {versus_hold['ci95']:6.2f}"
        )


def main() -> None:
    args = parse_args()
    report = run_diagnostic(args.episodes, args.seed)
    print_report(report)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
