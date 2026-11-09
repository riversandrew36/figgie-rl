"""Summarize a Phase 1 study: each learner minus Hold and Bayesian on shared deals."""

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
T_975 = {2: 4.302653, 3: 3.182446, 4: 2.776445, 5: 2.570582, 6: 2.446912, 7: 2.364624}


def profits(path: Path) -> np.ndarray:
    report = json.loads(path.read_text())
    return np.array([row["profit"] for row in report["per_episode"]], dtype=float)


def interval(values: list[float]) -> float:
    if len(values) < 2:
        return float("nan")
    critical = T_975[len(values) - 1]
    return float(critical * np.std(values, ddof=1) / np.sqrt(len(values)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    spec = yaml.safe_load(Path(args.config).read_text())
    folder = ROOT / "results" / spec["study_id"] / "exploratory"
    for lineup in spec["lineups"]:
        baselines = {
            name: profits(folder / f"{name}_{lineup}.json") for name in ("hold", "bayesian")
        }
        print(
            f"{spec['study_id']} {lineup}: "
            + ", ".join(f"{k} {v.mean():.2f}" for k, v in baselines.items())
        )
        for condition in spec["conditions"]:
            learners = [
                profits(folder / f"{condition}_{seed}_{lineup}.json") for seed in spec["seeds"]
            ]
            means = [float(x.mean()) for x in learners]
            line = f"  {condition:18} profit {np.mean(means):7.2f} seeds {np.round(means, 2).tolist()}"
            for name, base in baselines.items():
                edges = [float((x - base).mean()) for x in learners]
                half = interval(edges)
                verdict = "CLEARS" if np.mean(edges) - half > 0 else "no"
                line += f" | -{name} {np.mean(edges):+.2f} +/- {half:.2f} {verdict}"
            print(line)


if __name__ == "__main__":
    main()
