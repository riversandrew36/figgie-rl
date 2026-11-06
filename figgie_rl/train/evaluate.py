"""Evaluate a trained PPO model against scripted opponents."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from stable_baselines3 import PPO

from figgie_rl.agents.baselines import (
    PLAYING_STYLES,
    BayesianGoalTrader,
    BaselinePolicy,
    InventoryAwareMarketMaker,
    OpponentAction,
    RandomTrader,
    RuleBasedValueTrader,
    policy_for_difficulty,
)
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.train.metadata import json_ready, resolve_test_settings

AGENT_RNG_SEED_OFFSET = 500_000
REFERENCE_POLICY = "PPO"

EPISODE_FIELDS = (
    "episode",
    "seed",
    "agent_rng_seed",
    "policy",
    "profit",
    "win",
    "tie",
    "rank",
    "bankroll",
    "drawdown",
    "inventory_risk",
    "quote_fill_rate",
    "spread_capture",
)
AGGREGATE_FIELDS = (
    "policy",
    "episodes",
    "mean_profit",
    "profit_ci95",
    "win_rate",
    "tie_rate",
    "mean_rank",
    "mean_bankroll",
    "mean_drawdown",
    "mean_inventory_risk",
    "mean_quote_fill_rate",
    "mean_spread_capture",
)
PAIRED_FIELDS = (
    "reference",
    "other",
    "episodes",
    "mean_difference",
    "ci95",
    "beat_rate",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Figgie PPO model.")
    parser.add_argument("--model-path", type=str, required=True, help="Path to model .zip file.")
    parser.add_argument("--config", type=str, default="configs/ppo_simple.yaml", help="YAML config path.")
    parser.add_argument("--episodes", type=int, default=None, help="Number of eval episodes (default: 200).")
    parser.add_argument("--seed", type=int, default=None, help="Evaluation base seed (default: 101).")
    parser.add_argument(
        "--test", action="store_true",
        help="Use the configured reserved final-test range; incompatible with --seed/--episodes.",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help=(
            "Compare PPO with hold, random, market-maker, value-trader, Bayesian, "
            "hunter, banker, detective, and bluffer policies."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Optional .json or .csv path for per-episode results and aggregate metrics. "
            "CSV also writes sibling .aggregates.csv, .paired.csv, and .meta.csv files."
        ),
    )
    return parser.parse_args()


def load_config(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def compute_max_drawdown(values: list[float]) -> float:
    peak = -np.inf
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        dd = peak - v
        max_dd = max(max_dd, dd)
    return float(max_dd)


def encode_action(env: SimpleFiggieEnv, action: OpponentAction) -> int:
    return env.encode_semantic_action(action)


def _resolved_model_path(model_path: str) -> str:
    candidate = Path(model_path)
    if candidate.exists():
        return str(candidate.resolve())
    zipped = candidate if candidate.suffix == ".zip" else Path(str(candidate) + ".zip")
    if zipped.exists():
        return str(zipped.resolve())
    return str(candidate.resolve())


def _aggregate_policy(name: str, stats: dict[str, list[Any]]) -> dict[str, Any]:
    profits = stats["profits"]
    count = len(profits)
    return {
        "policy": name,
        "episodes": count,
        "mean_profit": statistics.fmean(profits),
        "profit_ci95": 1.96 * statistics.pstdev(profits) / (count ** 0.5),
        "win_rate": sum(stats["wins"]) / count,
        "tie_rate": sum(stats["ties"]) / count,
        "mean_rank": statistics.fmean(stats["ranks"]),
        "mean_bankroll": statistics.fmean(stats["bankrolls"]),
        "mean_drawdown": statistics.fmean(stats["drawdowns"]),
        "mean_inventory_risk": statistics.fmean(stats["inventory_risks"]),
        "mean_quote_fill_rate": statistics.fmean(stats["quote_fill_rates"]),
        "mean_spread_capture": statistics.fmean(stats["spread_capture"]),
    }


def _paired_rows(
    reference_name: str,
    results: dict[str, dict[str, list[Any]]],
) -> list[dict[str, Any]]:
    reference = results[reference_name]["profits"]
    rows: list[dict[str, Any]] = []
    for name, stats in results.items():
        if name == reference_name:
            continue
        differences = [left - right for left, right in zip(reference, stats["profits"])]
        standard_error = statistics.stdev(differences) / (len(differences) ** 0.5)
        rows.append(
            {
                "reference": reference_name,
                "other": name,
                "episodes": len(differences),
                "mean_difference": statistics.fmean(differences),
                "ci95": 1.96 * standard_error,
                "beat_rate": sum(value > 0 for value in differences) / len(differences),
            }
        )
    return rows


def run_evaluation(
    *,
    model_path: str,
    config_path: str,
    episodes: int | None,
    seed: int | None,
    benchmark: bool,
    test: bool = False,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    if test:
        if episodes is not None or seed is not None:
            raise ValueError("--test uses the configured range; omit --seed and --episodes")
        seed, episodes = resolve_test_settings(cfg)
    else:
        episodes = 200 if episodes is None else episodes
        seed = 101 if seed is None else seed
    if episodes <= 0:
        raise ValueError("--episodes must be >= 1")

    env_cfg = EnvConfig(**(dict(cfg["env"]) | {"seed": seed}))
    env = SimpleFiggieEnv(config=env_cfg)
    model = PPO.load(model_path)

    candidates: dict[str, BaselinePolicy | None] = {REFERENCE_POLICY: None}
    if benchmark:
        candidates.update(
            {
                "Hold": None,
                "Random": RandomTrader(),
                "Market maker": InventoryAwareMarketMaker(),
                "Value trader": RuleBasedValueTrader(),
                "Bayesian": BayesianGoalTrader(),
                **{style.capitalize(): policy_for_difficulty(style) for style in PLAYING_STYLES},
            }
        )

    results: dict[str, dict[str, list[Any]]] = {
        name: {
            "profits": [],
            "wins": [],
            "ties": [],
            "ranks": [],
            "bankrolls": [],
            "drawdowns": [],
            "inventory_risks": [],
            "quote_fill_rates": [],
            "spread_capture": [],
        }
        for name in candidates
    }
    per_episode: list[dict[str, Any]] = []
    for name, baseline in candidates.items():
        for episode in range(episodes):
            episode_seed = seed + episode
            obs, _ = env.reset(seed=episode_seed)
            agent_rng = np.random.default_rng(seed + AGENT_RNG_SEED_OFFSET + episode)
            done = False
            final_info: dict[str, Any] = {}
            reward_path = [0.0]
            while not done:
                if name == REFERENCE_POLICY:
                    action, _ = model.predict(obs, deterministic=True)
                    action_idx = int(action)
                elif name == "Hold":
                    action_idx = 0
                else:
                    assert baseline is not None
                    view = env._opponent_view(env.agent_idx)
                    action_idx = encode_action(env, baseline.act(view=view, rng=agent_rng))
                obs, reward, terminated, truncated, final_info = env.step(action_idx)
                reward_path.append(reward_path[-1] + float(reward))
                done = terminated or truncated

            winner_indices = final_info.get("winner_indices", [])
            profit = float(final_info.get("final_bankroll", 0.0)) - float(env.config.starting_cash)
            win = winner_indices == [env.agent_idx]
            tie = env.agent_idx in winner_indices and len(winner_indices) > 1
            rank = int(final_info.get("final_rank", env.config.num_players))
            bankroll = float(final_info.get("final_bankroll", 0.0))
            drawdown = compute_max_drawdown(reward_path)
            metrics = final_info.get("episode_metrics", {})
            inventory_risk = float(metrics.get("inventory_risk", 0.0))
            quote_fill_rate = float(metrics.get("quote_fill_rate", 0.0))
            spread_capture = float(metrics.get("avg_spread_capture", 0.0))

            stats = results[name]
            stats["profits"].append(profit)
            stats["wins"].append(win)
            stats["ties"].append(tie)
            stats["ranks"].append(rank)
            stats["bankrolls"].append(bankroll)
            stats["drawdowns"].append(drawdown)
            stats["inventory_risks"].append(inventory_risk)
            stats["quote_fill_rates"].append(quote_fill_rate)
            stats["spread_capture"].append(spread_capture)
            per_episode.append(
                {
                    "episode": episode,
                    "seed": episode_seed,
                    "agent_rng_seed": seed + AGENT_RNG_SEED_OFFSET + episode,
                    "policy": name,
                    "profit": profit,
                    "win": bool(win),
                    "tie": bool(tie),
                    "rank": rank,
                    "bankroll": bankroll,
                    "drawdown": drawdown,
                    "inventory_risk": inventory_risk,
                    "quote_fill_rate": quote_fill_rate,
                    "spread_capture": spread_capture,
                }
            )

    report = {
        "model_path": str(Path(model_path)),
        "model_path_resolved": _resolved_model_path(model_path),
        "config_path": str(Path(config_path).resolve()),
        "benchmark": bool(benchmark),
        "episodes": int(episodes),
        "base_seed": int(seed),
        "seeds": [seed + episode for episode in range(episodes)],
        "agent_rng_seeds": [seed + AGENT_RNG_SEED_OFFSET + episode for episode in range(episodes)],
        "policies": list(candidates),
        "configuration": {
            "evaluation_split": "test" if test else "exploratory",
            "starting_cash": float(env.config.starting_cash),
            "profit_definition": "final_bankroll - starting_cash",
            "paired_reference": REFERENCE_POLICY,
            "ci_method": {
                "aggregate_profit": "1.96 * population_stdev / sqrt(n)",
                "paired_difference": "1.96 * sample_stdev / sqrt(n)",
            },
            "env": json_ready(asdict(env.config)),
            "loaded_config": json_ready(cfg),
        },
        "per_episode": per_episode,
        "aggregates": [_aggregate_policy(name, stats) for name, stats in results.items()],
        "paired_profit_differences": _paired_rows(REFERENCE_POLICY, results) if benchmark else [],
    }
    env.close()
    return report


def print_report(report: dict[str, Any]) -> None:
    print(
        f"Benchmark across {report['episodes']} shared seeds; "
        "profit is final bankroll minus starting cash."
    )
    print("Seats, action order, and quote tie priority rotate independently each episode.")
    for row in report["aggregates"]:
        print(
            f"{row['policy']:>18}  profit={row['mean_profit']:8.2f} ± {row['profit_ci95']:6.2f} "
            f"(95% approx.)  "
            f"win={row['win_rate']:.3f}  "
            f"tie={row['tie_rate']:.3f}  "
            f"rank={row['mean_rank']:.3f}  "
            f"bankroll={row['mean_bankroll']:.2f}  "
            f"drawdown={row['mean_drawdown']:.2f}"
        )
        print(
            f"                  inventory risk={row['mean_inventory_risk']:.2f}  "
            f"quote fill={row['mean_quote_fill_rate']:.3f}  "
            f"spread capture={row['mean_spread_capture']:.2f}"
        )
    if report["benchmark"]:
        print("Paired profit differences by episode seed:")
        for row in report["paired_profit_differences"]:
            print(
                f"PPO minus {row['other']:>12}: {row['mean_difference']:8.2f} ± {row['ci95']:6.2f} "
                f"(95% approx. paired CI), beat rate={row['beat_rate']:.3f}"
            )


def _csv_cell(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_cell(row.get(key)) for key in fieldnames})


def _csv_output_paths(path: Path) -> dict[str, Path]:
    stem = path.with_suffix("")
    prefix = str(stem)
    return {
        "episodes": path,
        "aggregates": Path(prefix + ".aggregates.csv"),
        "paired": Path(prefix + ".paired.csv"),
        "meta": Path(prefix + ".meta.csv"),
    }


def write_evaluation_report(path: Path, report: dict[str, Any]) -> list[Path]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return [path]
    if suffix != ".csv":
        raise ValueError("--output must end with .json or .csv")

    paths = _csv_output_paths(path)
    _write_csv(paths["episodes"], EPISODE_FIELDS, report["per_episode"])
    _write_csv(paths["aggregates"], AGGREGATE_FIELDS, report["aggregates"])
    _write_csv(paths["paired"], PAIRED_FIELDS, report["paired_profit_differences"])
    configuration = report["configuration"]
    meta_rows = [
        {"key": "model_path", "value": report["model_path"]},
        {"key": "model_path_resolved", "value": report["model_path_resolved"]},
        {"key": "config_path", "value": report["config_path"]},
        {"key": "base_seed", "value": report["base_seed"]},
        {"key": "episodes", "value": report["episodes"]},
        {"key": "benchmark", "value": _csv_cell(report["benchmark"])},
        {"key": "policies", "value": ";".join(report["policies"])},
        {"key": "seeds", "value": ";".join(str(item) for item in report["seeds"])},
        {
            "key": "agent_rng_seeds",
            "value": ";".join(str(item) for item in report["agent_rng_seeds"]),
        },
        {"key": "starting_cash", "value": configuration["starting_cash"]},
        {"key": "profit_definition", "value": configuration["profit_definition"]},
        {"key": "paired_reference", "value": configuration["paired_reference"]},
        {"key": "configuration", "value": json.dumps(configuration, sort_keys=True)},
    ]
    _write_csv(paths["meta"], ("key", "value"), meta_rows)
    return [paths["episodes"], paths["aggregates"], paths["paired"], paths["meta"]]


def main() -> None:
    args = parse_args()
    if args.episodes is not None and args.episodes <= 0:
        raise ValueError("--episodes must be >= 1")
    if args.output is not None and Path(args.output).suffix.lower() not in {".json", ".csv"}:
        raise ValueError("--output must end with .json or .csv")

    report = run_evaluation(
        model_path=args.model_path,
        config_path=args.config,
        episodes=args.episodes,
        seed=args.seed,
        benchmark=args.benchmark,
        test=args.test,
    )
    print_report(report)
    if args.output:
        written = write_evaluation_report(Path(args.output), report)
        print("Wrote " + ", ".join(str(path) for path in written))


if __name__ == "__main__":
    main()
