"""Report the four-condition action-interface development comparison."""

from pathlib import Path
import hashlib
import json
import statistics
import csv
from datetime import datetime, timezone
import yaml
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/action_interfaces_20261106_v2"
SPEC = yaml.safe_load((OUT / "config.yaml").read_text())


def read(p):
    return json.loads(p.read_text())


def ci(values):
    return 4.302652729 * statistics.stdev(values) / len(values) ** 0.5


def main():
    frozen = read(OUT / "frozen_selection.json")
    for c in frozen["models"].values():
        assert hashlib.sha256(Path(c["model"]).read_bytes()).hexdigest() == c["sha256"]
    rows = []
    for condition in SPEC["conditions"]:
        for seed in SPEC["seeds"]:
            choice = frozen["models"][f"{condition}_{seed}"]
            for lineup in SPEC["lineups"]:
                r = read(OUT / "exploratory" / f"{condition}_{seed}_{lineup}.json")
                assert [x["seed"] for x in r["per_episode"]] == list(
                    range(
                        SPEC["exploratory"]["seed"],
                        SPEC["exploratory"]["seed"] + SPEC["exploratory"]["episodes"],
                    )
                )
                if choice["use_masking"]:
                    assert r["infeasible_fraction"] == 0
                rows.append(
                    {
                        "condition": condition,
                        "seed": seed,
                        "lineup": lineup,
                        "profit": r["mean_profit"],
                        "infeasible_fraction": r["infeasible_fraction"],
                        "trades": r["mean_trades"],
                        "top_action_fraction": r["top_action_fraction"],
                        "parameters": choice["parameter_count"],
                        "selected_steps": choice["timesteps"],
                    }
                )
    groups = []
    for lineup in SPEC["lineups"]:
        for condition in SPEC["conditions"]:
            matches = [
                r for r in rows if r["lineup"] == lineup and r["condition"] == condition
            ]
            vals = [r["profit"] for r in matches]
            groups.append(
                {
                    "lineup": lineup,
                    "condition": condition,
                    "mean_profit": statistics.mean(vals),
                    "seed_t95": ci(vals),
                    "infeasible_fraction": statistics.mean(
                        r["infeasible_fraction"] for r in matches
                    ),
                    "mean_trades": statistics.mean(r["trades"] for r in matches),
                    "top_action_fraction": statistics.mean(
                        r["top_action_fraction"] for r in matches
                    ),
                    "parameters": matches[0]["parameters"],
                }
            )
    effects = []
    for lineup in SPEC["lineups"]:
        for label, left, right in [
            ("Masking, flat", "flat_masked", "flat"),
            ("Masking, structured", "structured_masked", "structured"),
            ("Structure, unmasked", "structured", "flat"),
            ("Structure, masked", "structured_masked", "flat_masked"),
        ]:
            diff = [
                next(
                    r["profit"]
                    for r in rows
                    if r["lineup"] == lineup
                    and r["condition"] == left
                    and r["seed"] == seed
                )
                - next(
                    r["profit"]
                    for r in rows
                    if r["lineup"] == lineup
                    and r["condition"] == right
                    and r["seed"] == seed
                )
                for seed in SPEC["seeds"]
            ]
            effects.append(
                {
                    "lineup": lineup,
                    "contrast": label,
                    "mean_difference": statistics.mean(diff),
                    "seed_t95": ci(diff),
                    "seed_differences": diff,
                }
            )
    result = {
        "groups": groups,
        "effects": effects,
        "per_seed": rows,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (OUT / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    with (OUT / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = [
        "# Action masks and structured actions: implementation comparison",
        "",
        "This corrected run is `action_interfaces_20261106_v2`. An earlier partial run had a high-price mask mapping error; those reports remain archived in `action_interfaces_20261106` and are excluded from this analysis. Both interfaces are implemented and tested without changing the underlying market execution or settlement. A four-condition development study compares their effects independently: flat vs structured, with masking off vs on. Every condition used fresh training seeds 211, 223, 227 and 20,480 steps per seed. Selected weights were frozen before exploratory benchmarking.",
        "",
        "## Performance and feasibility",
        "",
        "Profit intervals below are t95 across three training-seed means (df=2), conditional on the same 100 exploratory deals per lineup. These are development results; they are not a new untouched final test.",
        "",
        "| Lineup | Condition | Mean profit ± seed t95 | Infeasible choices | Trades per round | Largest action fraction |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for g in groups:
        lines.append(
            f"| {g['lineup']} | {g['condition']} | {g['mean_profit']:.2f} ± {g['seed_t95']:.2f} | {g['infeasible_fraction']:.1%} | {g['mean_trades']:.2f} | {g['top_action_fraction']:.1%} |"
        )
    lines += [
        "",
        "The feasibility metric checks the pre-step public snapshot. It is distinct from a guaranteed fill: earlier actors can change the book, and passive quotes can remain unfilled. Masks require quote backing in the current state; they do not reserve cash/cards across multiple quotes. Masks do not exclude high prices when backed.",
        "",
        "## Paired intervention effects",
        "",
        "| Lineup | Contrast | Mean profit difference ± seed t95 |",
        "|---|---|---:|",
    ]
    for e in effects:
        lines.append(
            f"| {e['lineup']} | {e['contrast']} | {e['mean_difference']:+.2f} ± {e['seed_t95']:.2f} |"
        )
    lines += [
        "",
        "An interval crossing zero does not resolve an advantage. Three training seeds and a small budget provide limited evidence; zero infeasible actions is an interface correctness result, not proof of profitable play.",
        "",
        "## Reference policies",
        "",
        "| Lineup | Hold | Bayesian |",
        "|---|---:|---:|",
    ]
    for lineup in SPEC["lineups"]:
        h = read(OUT / "exploratory" / f"hold_{lineup}.json")
        b = read(OUT / "exploratory" / f"bayesian_{lineup}.json")
        lines.append(f"| {lineup} | {h['mean_profit']:.2f} | {b['mean_profit']:.2f} |")
    lines += [
        "",
        "## Interfaces and compatibility",
        "",
        "The structured policy computes P(kind), P(suit|kind), and P(price|quote kind,suit), then maps the joint distribution to the original 105 action indices. Final feasibility masking removes invalid leaves and renormalizes. It is not an independent MultiDiscrete tuple. The quote-price ladder, observations, engine, and settlement are unchanged. The flat and structured policies share the same feature/value MLP design but output-head parameter counts differ:",
    ]
    for condition in SPEC["conditions"]:
        g = next(g for g in groups if g["condition"] == condition)
        lines.append(f"- {condition}: {g['parameters']:,} total policy parameters.")
    lines += [
        "",
        "This difference is a capacity caveat when attributing structure effects. All conditions use MaskablePPO; unmasked controls explicitly disable masking during training and prediction. Existing PPO checkpoints keep their action encoding; new models must be loaded/evaluated through MaskablePPO with their recorded mask setting. The old generic evaluator and frozen-opponent adapter are not mask-aware.",
        "",
        "## Budget and artifacts",
        "",
        "245,760 new training steps total; two single-thread CPU workers. Two post-update checkpoints per run, selected on 40 validation deals by mean profit, win rate, then rank. No reward normalization, objective, price-ladder or opponent changes between conditions. No extra tuning followed exploration.",
        "",
        "- `manifest.json`, `config.yaml`: protocol/config/source hashes and dependencies.",
        "- `runs/`: stage weights, interface metadata, raw validation episodes, selected model pointers.",
        "- `frozen_selection.json`: frozen selected checkpoint hashes.",
        "- `exploratory/`: per-episode outcomes, action counts, feasibility rates, initial holdings, settlement outcomes.",
        "- `summary.json`, `summary.csv`, `action_interfaces.png` / `.svg`: analysis.",
        "",
        "Implementation verification covers empty books, cash/inventory checks, hidden-state invariance, self-quote exclusion, full-precision public prices, unchanged seeded trajectories, all 105 structured mappings, normalized initial probabilities, and checkpoint round trips. The complete local comparison smoke test exercises all four conditions. Models and results remain local.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for ax, lineup in zip(axes, SPEC["lineups"]):
        es = [e for e in effects if e["lineup"] == lineup]
        ax.errorbar(
            [e["mean_difference"] for e in es],
            range(len(es)),
            xerr=[e["seed_t95"] for e in es],
            fmt="o",
            color="#2166ac",
            capsize=5,
        )
        ax.set_yticks(range(len(es)), [e["contrast"] for e in es])
        ax.axvline(0, color="gray", linestyle="--")
        ax.set(
            title=lineup.title(),
            xlabel="Paired mean profit difference ± training-seed t95",
        )
    fig.suptitle("Action-interface development study · three training seeds")
    fig.savefig(OUT / "action_interfaces.png", dpi=180, bbox_inches="tight")
    fig.savefig(OUT / "action_interfaces.svg", bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({"groups": groups, "effects": effects}, indent=2))


if __name__ == "__main__":
    main()
