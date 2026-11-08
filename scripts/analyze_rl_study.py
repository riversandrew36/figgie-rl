"""Summarize frozen study results without selecting models. Requires matplotlib."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = yaml.safe_load((ROOT / "configs/rl_study.yaml").read_text())
OUT = ROOT / "results" / SPEC["study_id"]
SEEDS = SPEC["training_seeds"]
T95_DF2 = 4.302652729


def read(path: Path):
    return json.loads(path.read_text())


def interval(values):
    assert len(values) == 3, "This study's t interval is specified for three training seeds"
    return T95_DF2 * statistics.stdev(values) / len(values)**0.5


def ppo(report):
    return next(row for row in report["aggregates"] if row["policy"] == "PPO")


def collect():
    rows = []
    for lineup in ("familiar", "shifted"):
        for arm in ("fixed", "self_play"):
            for seed in SEEDS:
                name = f"{arm}_seed_{seed}"
                report = read(OUT / "final" / f"{name}_{lineup}.json")
                assert report["configuration"]["evaluation_split"] == "test"
                selection = read(OUT / "selection" / f"{name}.json")
                row = {"lineup": lineup, "method": arm, "training_seed": seed,
                       "checkpoint_timesteps": selection["selection"]["timesteps"], **ppo(report)}
                rows.append(row)
    return rows


def curves():
    histories = {arm: [] for arm in ("fixed", "self_play")}
    for seed in SEEDS:
        csv_path = ROOT / "artifacts" / f"{SPEC['study_id']}_fixed_seed_{seed}" / "eval_logs/bankroll_evaluations.csv"
        with csv_path.open() as handle:
            fixed = list(csv.DictReader(handle))
        histories["fixed"].append([float(row["mean_profit"]) for row in fixed])
        histories["self_play"].append([
            ppo(read(OUT / "validation" / f"self_play_seed_{seed}_iter_{i:03d}.json"))["mean_profit"]
            for i in range(SPEC["self_play_iterations"])
        ])
    return histories


def main():
    frozen = read(OUT / "frozen_selection.json")
    assert frozen["source_hashes"] == read(OUT / "manifest.json")["source_hashes"]
    rows = collect()
    summaries, differences = [], []
    for lineup in ("familiar", "shifted"):
        for arm in ("fixed", "self_play"):
            selected = [row for row in rows if row["lineup"] == lineup and row["method"] == arm]
            profits = [row["mean_profit"] for row in selected]
            summaries.append({"lineup": lineup, "method": arm,
                              "mean_profit": statistics.fmean(profits), "training_seed_t95": interval(profits),
                              "mean_win_rate": statistics.fmean(row["win_rate"] for row in selected),
                              "mean_rank": statistics.fmean(row["mean_rank"] for row in selected)})
        delta = [next(row["mean_profit"] for row in rows if row["lineup"] == lineup and row["method"] == "self_play" and row["training_seed"] == seed)
                 - next(row["mean_profit"] for row in rows if row["lineup"] == lineup and row["method"] == "fixed" and row["training_seed"] == seed)
                 for seed in SEEDS]
        differences.append({"lineup": lineup, "paired_seed_differences": dict(zip(SEEDS, delta)),
                            "mean_difference": statistics.fmean(delta), "training_seed_t95": interval(delta)})
    payload = {"analysis_dependencies": {"matplotlib": matplotlib.__version__, "numpy": np.__version__}, "specification": SPEC, "per_seed": rows, "method_summary": summaries,
               "self_play_minus_fixed": differences,
               "uncertainty": "Training-seed t95, df=2, conditional on the same 1000 final episode seeds; not a pooled independent 3000-episode interval."}
    (OUT / "summary.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (OUT / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    x = np.arange(1, 7) * SPEC["self_play_chunk_timesteps"] / 1000
    for arm, color, label in [("fixed", "#2166ac", "Fixed scripted opponents"), ("self_play", "#b35806", "Staged self-play")]:
        data = np.array(curves()[arm])
        mean, spread = data.mean(axis=0), data.std(axis=0, ddof=1)
        axes[0].plot(x, mean, "o-", color=color, label=label)
        axes[0].fill_between(x, mean-spread, mean+spread, color=color, alpha=0.12)
    axes[0].axhline(0, color="0.6", linewidth=0.8)
    axes[0].set(title="Validation learning curves", xlabel="Environment steps (thousands)", ylabel="Mean profit per round (chips)")
    axes[0].legend(frameon=False)
    axes[0].text(0, -0.23, "Lines: mean across 3 training seeds; shading: ±1 seed SD.\n200 validation deals, reused for checkpoint selection.", transform=axes[0].transAxes, fontsize=9)
    for i, diff in enumerate(differences):
        values = list(diff["paired_seed_differences"].values())
        axes[1].scatter(np.full(3, i)+[-0.07, 0, 0.07], values, s=40, color="#b35806", alpha=0.65)
        axes[1].errorbar(i, diff["mean_difference"], yerr=diff["training_seed_t95"], fmt="D", color="#222222", capsize=7, markersize=7)
    axes[1].axhline(0, color="0.5", linestyle="--", linewidth=1)
    axes[1].set_xticks([0, 1], ["Familiar lineup", "Shifted lineup"])
    axes[1].set(title="Held-out: self-play minus fixed", ylabel="Difference in mean profit (chips)", xlim=(-0.45, 1.45))
    axes[1].text(0, -0.23, "Dots: paired training seeds. Diamonds: mean ± t95 (df=2).\nConditional on the same 1,000 held-out deals per lineup.", transform=axes[1].transAxes, fontsize=9)
    fig.suptitle("Figgie RL: equal-budget fixed opponents vs staged self-play", fontsize=15)
    fig.savefig(OUT / "learning_and_final_results.png", dpi=180, bbox_inches="tight")
    fig.savefig(OUT / "learning_and_final_results.svg", bbox_inches="tight")
    plt.close(fig)

    standard = read(OUT / "final/standard_exogenous.json")
    sr = ppo(standard)
    lines = ["# Figgie RL: initial substantive experiment results", "", "The selected deterministic PPO policies were not competitive with the stronger scripted baselines in this study, and the three-seed comparison does not resolve a self-play advantage. A post-hoc diagnostic identifies a ranking mismatch between discounted marked-wealth reward and final cash as a concrete follow-up target; it does not establish the sole cause of training outcomes.", "", "## Design and audit trail", "",
             "Completed the legacy outside-book PPO run and a controlled player-quote comparison of fixed scripted opponents and six-stage self-play.", "",
             "- Comparison: 3 training seeds per method (7, 17, 27), 122,880 environment steps per run; 737,280 steps total.",
             "- Legacy run: 120,832 actual steps for 120,000 requested; combined training total 858,112 steps.",
             "- Both player-quote methods use supplied initial-hand Bayesian probabilities and flow features; this is not evidence of learning those features from raw observations.",
             "- Six candidates per run were compared on 200 validation episodes; final checkpoints were frozen before any final evaluation.",
             f"- Frozen at {frozen['frozen_at_utc']}. Source commit: {read(OUT / 'manifest.json')['source_commit']} plus the exact source hashes in manifest.json.",
             "- Final tests: 1,000 shared episode seeds per lineup. No post-test tuning or best-seed selection.",
             "- Self-play retains Hunter and Banker and substitutes one sampled frozen earlier policy for the third opponent. It is not four learned agents training symmetrically.", "",
             "## Held-out results by method", "",
             "Intervals below are t-based across **three training-seed means**, conditional on the same 1,000 evaluation deals. They do not capture all uncertainty about other deals or opponent populations.", "",
             "| Opponents | Training | Mean profit ± seed t95 | Outright win rate | Mean rank |",
             "|---|---|---:|---:|---:|"]
    for row in summaries:
        lines.append(f"| {row['lineup']} | {row['method']} | {row['mean_profit']:.2f} ± {row['training_seed_t95']:.2f} | {row['mean_win_rate']:.1%} | {row['mean_rank']:.2f} |")
    lines += ["", "Familiar: Hunter / Banker / Detective. Shifted: Banker / Detective / Bluffer.", "",
              "### Paired self-play-minus-fixed contrasts", ""]
    for d in differences:
        verdict = "The interval includes zero; this study does not resolve an advantage." if abs(d["mean_difference"]) <= d["training_seed_t95"] else (
            "The interval favors self-play in this specified evaluation." if d["mean_difference"] > 0 else "The interval favors fixed-opponent training in this specified evaluation.")
        lines.append(f"- **{d['lineup']}: {d['mean_difference']:+.2f} ± {d['training_seed_t95']:.2f} chips** (seed-level t95). {verdict}")
    lines += ["", "### Every training seed", "",
              "Profit intervals here are the evaluator's approximate episode-level 95% intervals for each fixed model, not training-seed intervals.", "",
              "| Lineup | Method | Training seed | Selected at steps | Mean profit ± episode CI | Win rate |",
              "|---|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['lineup']} | {row['method']} | {row['training_seed']} | {row['checkpoint_timesteps']:,} | {row['mean_profit']:.2f} ± {row['profit_ci95']:.2f} | {row['win_rate']:.1%} |")
    diagnostics = read(OUT / "action_diagnostics.json")
    lines += ["", "## What the selected policies actually do", "",
              "A post-selection behavioral diagnostic uses the first 50 previously exploratory deals, deterministic actions, and the frozen checkpoints. It does not change selection or use extra held-out deals. Each policy takes its single most common suit/price action on at least 96% of sampled steps. These results support a near-constant-quote description on this sample, not a claim of rich adaptive trading.", "",
              "| Model | Most common action | Fraction of sampled actions | Executed trades per round |", "|---|---|---:|---:|"]
    for name, diagnostic in diagnostics.items():
        details = diagnostic["action_details"]
        modal = max(details, key=details.get)
        fraction = details[modal] / sum(details.values())
        lines.append(f"| {name} | {modal} | {fraction:.1%} | {diagnostic['mean_executed_trades']:.2f} |")
    lines += ["", "The action-side totals, suit/price counts, and trade counts are in `action_diagnostics.json`. This describes greedy evaluation behavior; it does not measure the stochastic training policy's full action distribution."]
    lines += ["", "## Post-hoc reward-alignment diagnostic", "",
              "The endogenous reward is the change in marked wealth, with terminal settlement included. Undiscounted episode rewards telescope to final cash minus post-ante starting wealth; this equality was checked on all 300 diagnostic episodes. With gamma=0.99, early increases in last-trade-price inventory marks can outweigh a later settlement loss in discounted return. The final step receives only about 30.2% of the first step's discount weight over 120 steps.", "",
              "The following are descriptive means over the same 50 exploratory deals per policy, not additional held-out tests. Reward returns start after the $50 ante, so undiscounted return equals final profit plus $50.", "",
              "| Model | Discounted reward (gamma .99) | Undiscounted reward | Final profit |", "|---|---:|---:|---:|"]
    for name, diagnostic in diagnostics.items():
        lines.append(f"| {name} | {diagnostic['mean_discounted_return']:.2f} | {diagnostic['mean_undiscounted_return']:.2f} | {diagnostic['mean_final_profit']:.2f} |")
    lines += ["", "For example, fixed seed 17 has higher discounted reward than fixed seed 7 while losing substantially more final cash on these deals. This demonstrates a ranking mismatch for the sampled deterministic policies. It is consistent with the repeated expensive-quote behavior, but does not establish the sole cause of training outcomes.", "",
              "For marked wealth V and T steps, the arithmetic is:", "",
              "```text", "sum[t=0..T-1] gamma^t (V[t+1] - V[t])",
              "= -V[0] + (1-gamma) sum[t=1..T-1] gamma^(t-1) V[t] + gamma^(T-1) V[T]", "```", "",
              "Thus gamma below one puts positive weight on intermediate marked wealth, in addition to final cash. A follow-up should compare an undiscounted finite-horizon objective or discount-consistent potential shaping against the current reward, with new test seeds and the same computational budget. No such fix or retraining was made in this study."]
    fig2, ax2 = plt.subplots(1, 2, figsize=(13, 5.3), constrained_layout=True)
    trace = diagnostics["fixed_seed_17"]["first_episode_trace"]
    ax2[0].plot([v["step"] for v in trace], [v["marked_wealth"] for v in trace], color="#2166ac", label="Simulator marked wealth")
    ax2[0].plot([v["step"] for v in trace], [v["cash"] for v in trace], color="#b35806", label="Cash / terminal bankroll")
    ax2[0].axhline(300, color="0.6", linestyle="--", linewidth=1)
    ax2[0].set(title="One exploratory deal: repeated $60 club bids", xlabel="Step", ylabel="Chips")
    ax2[0].legend(frameon=False, fontsize=9)
    keys = list(diagnostics)
    positions = np.arange(len(keys))
    ax2[1].bar(positions-0.18, [diagnostics[k]["mean_discounted_return"] for k in keys], width=.36, color="#2166ac", label="Discounted reward, gamma .99")
    ax2[1].bar(positions+0.18, [diagnostics[k]["mean_undiscounted_return"] for k in keys], width=.36, color="#b35806", label="Undiscounted reward")
    ax2[1].axhline(0, color="0.5", linewidth=.8)
    ax2[1].set_xticks(positions, ["F7", "F17", "F27", "S7", "S17", "S27"])
    ax2[1].set(title="Same policies, different reward ranking", ylabel="Mean episode reward return")
    ax2[1].legend(frameon=False, fontsize=9)
    ax2[1].text(0, -.22, "50 exploratory deals per model; F=fixed, S=self-play.\nReward baseline is post-ante; final profit = undiscounted reward - 50.", transform=ax2[1].transAxes, fontsize=9)
    fig2.savefig(OUT / "reward_alignment_diagnostic.png", dpi=180, bbox_inches="tight")
    plt.close(fig2)
    lines += ["", "## Scripted reference policies", "",
              "Each policy occupies the learner seat against the stated three-opponent lineup. These are not results from a free-for-all tournament. Baseline reports are computed once per lineup and reused with new paired differences for each PPO model.", "",
              "| Policy | Familiar mean profit ± episode CI | Shifted mean profit ± episode CI |", "|---|---:|---:|"]
    familiar = read(OUT / "final/fixed_seed_7_familiar.json")
    shifted = read(OUT / "final/fixed_seed_7_shifted.json")
    for row in familiar["aggregates"]:
        if row["policy"] == "PPO":
            continue
        other = next(r for r in shifted["aggregates"] if r["policy"] == row["policy"])
        lines.append(f"| {row['policy']} | {row['mean_profit']:.2f} ± {row['profit_ci95']:.2f} | {other['mean_profit']:.2f} ± {other['profit_ci95']:.2f} |")
    lines += ["", "## Legacy outside-book experiment", "",
              f"Validation-selected PPO: **{sr['mean_profit']:.2f} ± {sr['profit_ci95']:.2f} chips** mean profit over 1,000 reserved final episodes; outright wins {sr['win_rate']:.1%}, mean rank {sr['mean_rank']:.2f}.",
              "This is one training seed in a different market against weak / average / Bayesian opponents. Do not compare its profit directly with the player-quote study.", "",
              "## Interpretation and limits", "",
              "The comparison concerns complete training procedures: self-play resets environments and saves checkpoints after each stage, while fixed training is continuous and its existing callback saves during rollout collection. It does not isolate opponent adaptation from staging or checkpoint timing.", "",
              "A supplied goal posterior, a small MLP policy, a discrete quote ladder, one training budget, and two scripted opponent lineups constrain these findings. Three training seeds are a starting point, not a broad survey. Positive simulator profit is not evidence of human-level Figgie play or real-world trading skill.", "",
              "The final-test ranges have now been examined. Reserve new ranges before any future experiment that uses these findings for a design decision. Keep the completed reports unchanged.", "",
              "Drawdown columns in raw evaluator output refer to the cumulative dense-reward path and should not be described as independently measured bankroll drawdown.", "",
              "## Local artifacts", "",
              "- `manifest.json`: source/config hashes and dependency versions.",
              "- `frozen_selection.json`: selected checkpoint hashes and protocol before final tests.",
              "- `configs/`, `logs/`, `validation/`, `exploratory/`, `final/`: exact inputs and raw reports.",
              "- `summary.json`, `summary.csv`: per-seed results and method contrasts.",
              "- `learning_and_final_results.png` / `.svg`: validation and final comparisons.",
              "- `reward_alignment_diagnostic.png`: post-hoc reward/cash comparison.",
              "- Model weights and sidecars: `artifacts/rl_study_20261106_*` and `artifacts/ppo_goal_belief_v2/`.", "",
              "The study and its model files have not been published automatically. The public demo continues to show scripted baselines."]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"method_summary": summaries, "contrasts": differences, "standard_ppo": sr}, indent=2))


if __name__ == "__main__":
    main()
