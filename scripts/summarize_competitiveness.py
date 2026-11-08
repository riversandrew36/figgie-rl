"""Summarize completed local pilots without opening a final-test range."""

import hashlib
import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/figgie_competitiveness_20261106_pilot"


def read(p):
    return json.loads(p.read_text())


reward = []
for p in sorted(OUT.glob("*_exploratory.json")):
    r = read(p)
    a = {x["policy"]: x for x in r["aggregates"]}
    reward.append(
        {
            "condition": p.stem.replace("_exploratory", ""),
            "profit": a["PPO"]["mean_profit"],
            "hold": a["Hold"]["mean_profit"],
            "bayesian": a["Bayesian"]["mean_profit"],
        }
    )
imitation = read(OUT / "imitation/summary.json")
pool = []
for p in sorted((OUT / "pool").glob("*_evaluation.json")):
    r = read(p)
    a = {x["policy"]: x for x in r["aggregates"]}
    hold = next(x for x in r["paired_profit_differences"] if x["other"] == "Hold")
    pool.append(
        {
            "condition": p.stem,
            "profit": a["PPO"]["mean_profit"],
            "hold": a["Hold"]["mean_profit"],
            "bayesian": a["Bayesian"]["mean_profit"],
            "hold_difference": hold["mean_difference"],
            "hold_ci95": hold["ci95"],
        }
    )
summary = {
    "reward_pilots": reward,
    "imitation_pilots": imitation,
    "pool_pilots": pool,
    "status": "Main training complete; final testing not started. Stopped analysis at user request to finish now.",
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
lines = [
    "# Competitiveness follow-up: completed local evidence",
    "",
    "All four approaches were implemented and tested at pilot scale. The historical-pool approach was advanced to a three-seed training comparison. All six 122,880-step main runs completed. Final evaluation was not started; remaining analysis processes were stopped when the user requested a wrap-up. No new final-test range was opened.",
    "",
    "## Pilot reward alignment",
    "",
    "100 exploratory episodes per condition; all share the same hands/opponents.",
    "",
    "| Condition | PPO profit | Hold | Bayesian |",
    "|---|---:|---:|---:|",
]
for r in reward:
    lines.append(
        f"| {r['condition']} | {r['profit']:.2f} | {r['hold']:.2f} | {r['bayesian']:.2f} |"
    )
lines += [
    "",
    "All four conditions also trailed Hold on their 100-episode validation split. These small pilots do not establish that objective alignment is ineffective; sparse reward and limited training remain plausible limits. Reward normalization was not changed.",
    "",
    "## Teacher imitation",
    "",
    "Each teacher supplied 3,000 transitions from its own player view. Separate clones were trained for 8 epochs and fine-tuned for 20,480 PPO steps. Teacher action-agreement validation used disjoint demonstration episodes. The test suite checks observations and action-label shape/range; hidden goal labels are not included.",
    "",
    "| Teacher | Validation agreement | BC profit | BC + PPO profit |",
    "|---|---:|---:|---:|",
]
for t in ["bayesian", "hunter", "banker", "detective", "bluffer"]:
    a = next(x for x in imitation if x["teacher"] == t and x["phase"] == "bc")
    b = next(x for x in imitation if x["teacher"] == t and x["phase"] == "bc_ppo")
    lines.append(
        f"| {t} | {a['agreement']:.1%} | {a['profit']:.2f} | {b['profit']:.2f} |"
    )
lines += [
    "",
    "The common Hold result was −7.63 and Bayesian +10.16. No clone reliably beat Hold or preserved the strongest teacher performance. Fine-tuning did not improve this pattern.",
    "",
    "## Diverse historical checkpoint pool",
    "",
    "Matched 40,960-step one-seed controls were evaluated on 100 exploratory episodes per lineup. The pool uses six prior checkpoints plus its growing own history, two sampled learned opponents and one scripted opponent.",
    "",
    "| Condition | PPO profit | Hold | Bayesian | PPO − Hold ± episode CI |",
    "|---|---:|---:|---:|---:|",
]
for r in pool:
    lines.append(
        f"| {r['condition']} | {r['profit']:.2f} | {r['hold']:.2f} | {r['bayesian']:.2f} | {r['hold_difference']:+.2f} ± {r['hold_ci95']:.2f} |"
    )
lines += [
    "",
    "The pool is the most promising completed pilot, but one training seed and 100 deals do not establish robustness. The shifted-lineup paired interval just clears zero against Hold; it does not clearly beat Bayesian.",
    "",
    "## Main run status and limitations",
    "",
    "Six main training runs completed: fixed opponents and historical pool, seeds 49, 59, 69, each 122,880 steps. Checkpoint selection is complete for five runs, and the remaining selection can be resumed. No frozen finalist manifest or final reports were produced.",
    "",
    "Seed 49 was reused from the pilot and should be treated as development evidence; a robust confirmation should add a fresh third training seed or explicitly exclude seed 49 from the primary inference. Fixed training was continuous while self-play reset at stage boundaries, so this compares complete procedures rather than isolating opponent diversity.",
    "",
    "## Compute and reproducibility",
    "",
    "Main training used 737,280 PPO environment steps. Reward pilots used 81,920; imitation fine-tuning 102,400; matched pool/control pilots used 122,880, plus a preserved failed 10,240-step pool attempt. Training total: 1,054,720 steps, below the 2,000,000 training-step cap. Demonstration generation used 15,000 training transitions and 6,000 validation transitions. BC presented 120,000 training samples over eight epochs. Evaluation costs are additional and are retained in raw per-episode reports. Main orchestration used two workers, one Torch/BLAS thread each; no paid compute.",
    "",
    "Raw reports and model checkpoints remain local. Main configurations, source hashes and historical checkpoint hashes are under `results/figgie_competitiveness_20261106_expanded/manifest.json`. Pilot source/config hashes are saved with this report. The old final ranges remain consumed; the new main final range 1509000–1509999 remains unopened.",
    "",
    "## Recommendation",
    "",
    "Complete an independent three-seed confirmation of the historical pool, with fixed and self-play staging matched, before making a competitiveness claim. Improve imitation data coverage and validation agreement before scaling it. Treat reward alignment as a correctness prerequisite, and use behavioral diagnostics to check for constant-action strategies. Do not tune on a final-test range once it is inspected.",
]
(OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
files = [
    *sorted((ROOT / "figgie_rl").rglob("*.py")),
    *sorted((ROOT / "scripts").glob("*competiti*.py")),
    ROOT / "scripts/run_imitation_pilot.py",
    ROOT / "configs/competitiveness_pilot.yaml",
    ROOT / "configs/competitiveness_main.yaml",
]
(OUT / "source_hashes.json").write_text(
    json.dumps(
        {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
        indent=2,
    )
    + "\n"
)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
axes[0].barh(
    [r["condition"].replace("_gamma_", " γ ").replace("_", " ") for r in reward],
    [r["profit"] for r in reward],
    color="#2166ac",
)
axes[0].axvline(-2.83, color="black", linestyle="--", label="Hold")
axes[0].set(title="Reward pilots", xlabel="Mean profit (100 exploratory deals)")
axes[0].legend()
axes[1].barh(
    [r["condition"].replace("_evaluation", "").replace("_", " ") for r in pool],
    [r["hold_difference"] for r in pool],
    xerr=[r["hold_ci95"] for r in pool],
    color="#b35806",
    capsize=4,
)
axes[1].axvline(0, color="black", linestyle="--")
axes[1].set(
    title="Pool pilot: PPO minus Hold",
    xlabel="Paired mean difference ± approximate 95% CI",
)
fig.savefig(OUT / "pilot_results.png", dpi=180, bbox_inches="tight")
print(OUT / "REPORT.md")
