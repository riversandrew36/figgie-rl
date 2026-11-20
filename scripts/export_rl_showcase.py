"""Export the archived strong-ladder results and embed them for file:// use."""

import csv
import hashlib
import json
from pathlib import Path
from statistics import mean

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/strong_ladder.yaml"
ARENA = ROOT / "figgie_rl/arena"
RESULTS = ROOT / "results/strong_ladder_20261115"
START = '<script type="application/json" id="rlShowcaseData">'
# The revision that introduced the strong-ladder study runner and config.
STUDY_CODE = "f8d83767285065d3499f2e3775d40f0152e27e36"


def build_showcase(results: Path = RESULTS) -> dict:
    raw_config = CONFIG.read_bytes()
    config = yaml.safe_load(raw_config)
    steps = []
    hold = None
    for step in config["steps"]:
        number, name = step["number"], step["name"]
        folder = results / f"step_{number}_{name}"
        summary = json.loads((folder / "summary.json").read_text())
        with (folder / "curve.csv").open(newline="") as stream:
            curve = [
                [int(row["seed"]), int(row["timesteps"]), float(row["mean_profit"])]
                for row in csv.DictReader(stream)
            ]
        assert curve == [
            [row["seed"], row["timesteps"], row["mean_profit"]] for row in summary["curve"]
        ]
        if hold is not None:
            assert hold == summary["hold_profit"]
        hold = summary["hold_profit"]
        series = [
            {"seed": seed, "points": [[tick, profit] for key, tick, profit in curve if key == seed]}
            for seed in config["seeds"]
        ]
        finals = [line["points"][-1][1] for line in series]
        steps.append({
            "number": number, "name": name, "series": series, "final": finals, "mean": mean(finals),
        })
    evaluation = config["evaluation"]
    return {
        "study": config["study_id"],
        "config_sha256": hashlib.sha256(raw_config).hexdigest(),
        "study_code_revision": STUDY_CODE,
        "evaluation_seeds": [evaluation["seed"], evaluation["seed"] + evaluation["episodes"] - 1],
        # The archived per-step summaries only record Hold. Other baselines are
        # the rounded values in PROJECT_STATUS.md, in the strong-lineup section.
        "baselines": {"Hold": hold, "Bayesian": 3.41, "Hunter": 8.40, "Bluffer": 7.36},
        "steps": steps,
    }


def main() -> None:
    payload = json.dumps(build_showcase(), separators=(",", ":"), allow_nan=False)
    (ARENA / "rl_results.json").write_text(payload + "\n")
    html = ARENA / "figgie_play.html"
    before, _, tail = html.read_text().partition(START)
    if not tail:
        raise ValueError("Missing inline results marker")
    _, _, after = tail.partition("</script>")
    html.write_text(before + START + payload + "</script>" + after)


if __name__ == "__main__":
    main()
