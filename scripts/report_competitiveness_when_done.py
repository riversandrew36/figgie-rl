"""Write a local result summary when all predeclared final reports exist."""

import json
import statistics
import time
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = yaml.safe_load((ROOT / "configs/competitiveness_main.yaml").read_text())
OUT = ROOT / "results" / SPEC["study_id"]
paths = [
    OUT / "final" / f"{arm}_seed_{seed}_{lineup}.json"
    for arm in ("fixed", "self_play")
    for seed in SPEC["training_seeds"]
    for lineup in ("familiar", "shifted")
]
for _ in range(720):
    if all(p.exists() for p in paths):
        break
    time.sleep(10)
else:
    raise RuntimeError("Final reports incomplete after two-hour reporting window")
rows = []
for p in paths:
    r = json.loads(p.read_text())
    a = next(x for x in r["aggregates"] if x["policy"] == "PPO")
    rows.append({"file": p.name, **a})
lines = [
    "# Competitiveness follow-up: local final results",
    "",
    "This summary follows completed pilots of reward alignment, teacher cloning/fine-tuning, and historical checkpoint pools. The historical pool was promoted to the three-seed matched-budget comparison.",
    "",
    "| Lineup | Method | Mean profit | Training-seed t95 |",
    "|---|---|---:|---:|",
]
for lineup in ("familiar", "shifted"):
    for arm in ("fixed", "self_play"):
        vals = [
            x["mean_profit"]
            for x in rows
            if x["file"].startswith(arm + "_seed_")
            and x["file"].endswith("_" + lineup + ".json")
        ]
        lines.append(
            f"| {lineup} | {arm} | {statistics.mean(vals):.2f} | {4.302652729 * statistics.stdev(vals) / len(vals) ** 0.5:.2f} |"
        )
lines += [
    "",
    "Intervals use three training-seed means, conditional on shared held-out deals. Seed 49 was used in the pool pilot; treat it as a reused development seed and report that dependence when interpreting this comparison. The fixed trainer runs continuously while self-play resets at stage boundaries, so differences concern complete procedures.",
    "",
    "Final data have now been examined. Reserve new ranges before further tuning. Raw reports, frozen selections, configurations, checkpoint hashes, and model artifacts remain local.",
]
(OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
(OUT / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
print("Saved", OUT / "REPORT.md")
