from pathlib import Path
import json
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
pool = root / "results/figgie_competitiveness_20261106_pilot/pool"
runs = [
    (
        "fixed",
        root
        / "artifacts/figgie_competitiveness_20261106_pool_fixed_seed_49/best_model/best_model.zip",
    ),
    (
        "selfplay",
        root
        / "artifacts/figgie_competitiveness_20261106_pool_seed_49/self_play/checkpoints/iter_003.zip",
    ),
]
for method, model in runs:
    for lineup in ("familiar", "shifted"):
        cfg = pool / f"{method}_{lineup}.yaml"
        out = pool / f"{method}_{lineup}_evaluation.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "figgie_rl.train.evaluate",
                "--config",
                str(cfg),
                "--model-path",
                str(model),
                "--episodes",
                "100",
                "--seed",
                "1503100",
                "--benchmark",
                "--output",
                str(out),
            ],
            cwd=root,
            check=True,
            stdout=out.with_suffix(".log").open("w"),
            stderr=subprocess.STDOUT,
        )
        r = json.loads(out.read_text())
        print(
            method,
            lineup,
            [(a["policy"], round(a["mean_profit"], 2)) for a in r["aggregates"][:3]],
            flush=True,
        )
