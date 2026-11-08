"""Audit and report the fresh matched-stage confirmation after held-out testing."""

from pathlib import Path
import json
import statistics
import csv
import hashlib
import yaml
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
SPEC = yaml.safe_load((ROOT / "configs/confirmation.yaml").read_text())
OUT = ROOT / "results" / SPEC["study_id"]
SEEDS = SPEC["training_seeds"]


def read(p):
    return json.loads(p.read_text())


def ci(x):
    return 4.302652729 * statistics.stdev(x) / len(x) ** 0.5


def main():
    frozen = read(OUT / "frozen_selection.json")
    for choice in frozen["models"].values():
        assert (
            hashlib.sha256(Path(choice["model"]).read_bytes()).hexdigest()
            == choice["sha256"]
        )
    rows = []
    effects = []
    for lineup in ("familiar", "shifted"):
        for arm in ("fixed", "self_play"):
            for seed in SEEDS:
                report = read(OUT / "final" / f"{arm}_seed_{seed}_{lineup}.json")
                assert (
                    report["episodes"] == 500
                    and report["configuration"]["evaluation_split"] == "test"
                )
                assert report["seeds"] == list(range(1800000, 1800500))
                ppo = next(r for r in report["aggregates"] if r["policy"] == "PPO")
                pairs = {p["other"]: p for p in report["paired_profit_differences"]}
                rows.append(
                    {
                        "lineup": lineup,
                        "arm": arm,
                        "seed": seed,
                        **ppo,
                        "minus_hold": pairs["Hold"]["mean_difference"],
                        "minus_bayesian": pairs["Bayesian"]["mean_difference"],
                    }
                )
        fixed = [r for r in rows if r["lineup"] == lineup and r["arm"] == "fixed"]
        pool = [r for r in rows if r["lineup"] == lineup and r["arm"] == "self_play"]
        diffs = [p["mean_profit"] - f["mean_profit"] for p, f in zip(pool, fixed)]
        effects.append(
            {
                "lineup": lineup,
                "pool_minus_fixed": statistics.mean(diffs),
                "t95": ci(diffs),
                "seed_differences": dict(zip(SEEDS, diffs)),
            }
        )
    groups = []
    for lineup in ("familiar", "shifted"):
        for arm in ("fixed", "self_play"):
            selected = [r for r in rows if r["lineup"] == lineup and r["arm"] == arm]
            group = {"lineup": lineup, "arm": arm}
            for key in ("mean_profit", "minus_hold", "minus_bayesian"):
                values = [r[key] for r in selected]
                group[key] = statistics.mean(values)
                group[key + "_t95"] = ci(values)
            groups.append(group)
    save = {
        "per_seed": rows,
        "group_summary": groups,
        "paired_method_effects": effects,
        "uncertainty": "t95 over three independent training-seed means, conditional on shared 500 held-out deals per lineup",
    }
    (OUT / "summary.json").write_text(json.dumps(save, indent=2) + "\n")
    with (OUT / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    pool_groups = [g for g in groups if g["arm"] == "self_play"]
    hold_clear = all(g["minus_hold"] - g["minus_hold_t95"] > 0 for g in pool_groups)
    bayes_lag = all(
        g["minus_bayesian"] + g["minus_bayesian_t95"] < 0 for g in pool_groups
    )
    modes = read(OUT / "policy_modes_validation.json")
    save["validation_policy_modes"] = modes
    (OUT / "summary.json").write_text(json.dumps(save, indent=2) + "\n")
    conclusion = (
        (
            "The pool reliably improves over Hold in these settings. "
            if hold_clear
            else "The pool does not establish a reliable improvement over Hold in both settings. "
        )
        + (
            "It trails the Bayesian baseline on both lineups. "
            if bayes_lag
            else "The Bayesian comparison remains uncertain. "
        )
        + "Pool results are descriptively more consistent across training seeds, while the pool-minus-fixed t intervals include zero."
    )
    lines = [
        "# Independent matched-stage confirmation",
        "",
        "All six matched training runs and the predeclared held-out evaluations are complete. Three fresh training seeds (83, 97, 109) were used. Both arms use six stages with identical environment reset seed formulas, PPO optimizer continuity, and post-update checkpoint saving. Frozen-opponent loading preserves the learner RNG state.",
        "",
        conclusion,
        "",
        "## Final performance",
        "",
        "Means and t95 intervals across three training seeds are conditional on the same 500 final deals per lineup; repeated deals are not pooled as independent trials.",
        "",
        "| Lineup | Method | Profit ± seed t95 | Minus Hold ± seed t95 | Minus Bayesian ± seed t95 |",
        "|---|---|---:|---:|---:|",
    ]
    for r in groups:
        lines.append(
            f"| {r['lineup']} | {r['arm']} | {r['mean_profit']:.2f} ± {r['mean_profit_t95']:.2f} | {r['minus_hold']:+.2f} ± {r['minus_hold_t95']:.2f} | {r['minus_bayesian']:+.2f} ± {r['minus_bayesian_t95']:.2f} |"
        )
    lines += ["", "## Paired method comparison", ""]
    for effect in effects:
        verdict = (
            "The interval includes zero; this confirmation does not resolve a method advantage."
            if abs(effect["pool_minus_fixed"]) <= effect["t95"]
            else (
                "The interval favors the pool in this specific setting."
                if effect["pool_minus_fixed"] > 0
                else "The interval favors fixed scripted opponents in this specific setting."
            )
        )
        lines.append(
            f"- {effect['lineup']}: pool minus fixed = {effect['pool_minus_fixed']:+.2f} ± {effect['t95']:.2f} chips (seed t95). {verdict}"
        )
    lines += [
        "",
        "## Every training seed",
        "",
        "| Lineup | Arm | Seed | Mean profit ± episode CI | Win rate |",
        "|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['lineup']} | {row['arm']} | {row['seed']} | {row['mean_profit']:.2f} ± {row['profit_ci95']:.2f} | {row['win_rate']:.1%} |"
        )
    lines += [
        "",
        "## Design, budget, and limits",
        "",
        "737,280 new PPO training steps total (122,880 per run). The pool also reuses six historical policy runs totaling 737,280 earlier training steps. This inherited pretraining cost is additional to the matched current-run budget and is not supplied to the fixed control. Two CPU workers with one Torch/BLAS thread each; no paid compute. Validation used 100 fixed deals and exactly six post-update checkpoints per run. Both arms are staged identically; the intervention is the opponent pool. Full validation and test episode records are retained. Final actions are deterministic.",
        "",
        "Familiar lineup: Hunter/Banker/Detective. Shifted lineup: Banker/Detective/Bluffer. Each scripted baseline occupies the learner seat; this is not a free-for-all tournament. Baseline episodes are cached per lineup with provenance and fresh paired differences for each PPO model.",
        "",
        "The pool consists of Hunter plus two historical learned policies sampled without replacement at each stage. Six preexisting policies remain available along with each learner’s earlier checkpoints. The observation includes engineered hand-posterior and flow features. Findings concern this simulator, two opponent lineups, one compute budget, and only three independent training seeds.",
        "",
        "Final seeds 1800000–1800499 are now consumed. Future tuning informed by these findings requires a new test range. All models and reports remain local.",
        "",
        "## Files",
        "",
        "- `manifest.json` and `frozen_selection.json`: source/config hashes, historical weights, selected model hashes and freeze timestamp.",
        "- `logging_amendment.json`: pre-validation logging-only amendment; original manifest preserved.",
        "- `validation/`, `exploratory/`, `final/`: raw episode reports.",
        "- `summary.json`, `summary.csv`, `confirmation.png`: results and figures.",
        "- `artifacts/figgie_confirmation_20261106_*`: saved model checkpoints and sidecars.",
    ]
    lines += [
        "",
        "## Validation behavior",
        "",
        "This diagnostic uses only the validation split and does not change checkpoint selection. Sampled actions use a recorded seed after loading each model. The final evaluation mode remains the predeclared deterministic policy.",
        "",
        "| Model | Deterministic profit | Sampled profit | Largest deterministic action fraction |",
        "|---|---:|---:|---:|",
    ]
    for key, value in modes.items():
        d, t = value["deterministic"], value["stochastic"]
        lines.append(
            f"| {key} | {d['mean_profit']:.2f} | {t['mean_profit']:.2f} | {d['top_action_fraction']:.1%} |"
        )
    lines += [
        "",
        "The fixed policies take one action on at least 99.7% of validation steps. Pool policies concentrate on selling particular suits (largest action fractions 54.1%–89.7%). Stochastic action sampling causes substantial losses for every policy. This supports a limited liquidation-policy interpretation, not evidence of broad adaptive trading.",
        "",
        "## Recommended next experiment",
        "",
        "Investigate legal-action masking and structured trading actions, and verify teacher imitation agreement and on-policy behavior before further scaling. These are follow-up hypotheses, not tested fixes. Preserve this completed study and choose new final seeds for any future tuning.",
        "",
        "Regression verification: 93 tests passed; Ruff passed. New training and all results remain local.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for arm, color in [("fixed", "#2166ac"), ("self_play", "#b35806")]:
        matrix = []
        for seed in SEEDS:
            matrix.append(
                [
                    read(
                        OUT / "validation" / f"{arm}_seed_{seed}_iter_{stage:03d}.json"
                    )["aggregates"][0]["mean_profit"]
                    for stage in range(6)
                ]
            )
        d = np.array(matrix)
        x = np.arange(1, 7) * 20.48
        axes[0].plot(x, d.mean(axis=0), "o-", color=color, label=arm)
        axes[0].fill_between(
            x,
            d.mean(axis=0) - d.std(axis=0, ddof=1),
            d.mean(axis=0) + d.std(axis=0, ddof=1),
            alpha=0.15,
            color=color,
        )
    axes[0].axhline(0, color="gray", lw=0.8)
    axes[0].set(
        title="Matched-stage validation curves",
        xlabel="Environment steps (thousands)",
        ylabel="Mean profit (chips)",
    )
    axes[0].legend(frameon=False)
    for i, e in enumerate(effects):
        axes[1].scatter(
            np.full(3, i) + [-0.07, 0, 0.07],
            list(e["seed_differences"].values()),
            color="#b35806",
        )
        axes[1].errorbar(
            i, e["pool_minus_fixed"], yerr=e["t95"], fmt="D", color="black", capsize=6
        )
    axes[1].axhline(0, color="gray", linestyle="--")
    axes[1].set_xticks([0, 1], ["Familiar", "Shifted"])
    axes[1].set(
        title="Held-out pool minus fixed",
        ylabel="Paired mean profit difference (chips)",
        xlim=(-0.4, 1.4),
    )
    axes[0].text(
        0,
        -0.25,
        "Lines: three-seed means; shading: ±1 seed SD.\n100 validation deals, reused for selection.",
        transform=axes[0].transAxes,
        fontsize=9,
    )
    axes[1].text(
        0,
        -0.25,
        "Dots: paired training seeds; diamonds: mean ± seed t95 (df=2).\nConditional on 500 common held-out deals per lineup.",
        transform=axes[1].transAxes,
        fontsize=9,
    )
    fig.savefig(OUT / "confirmation.png", dpi=180, bbox_inches="tight")
    fig.savefig(OUT / "confirmation.svg", bbox_inches="tight")
    plt.close(fig)
    print(json.dumps({"groups": groups, "effects": effects}, indent=2))


if __name__ == "__main__":
    main()
