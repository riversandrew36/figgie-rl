"""Console entry point for the source-checkout research harness."""

from pathlib import Path
import os
import subprocess
import sys


def main():
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        from figgie_rl.train.action_study import main as study_main

        study_main()
        return
    root = Path.cwd()
    if not (root / "figgie_rl/train/action_study.py").is_file():
        raise SystemExit(
            "Run figgie-action-study from the Figgie source checkout (configs and protocol are required)."
        )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root) + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    result = subprocess.run(
        [sys.executable, "-m", "figgie_rl.train.action_study", *sys.argv[1:]],
        cwd=root,
        env=environment,
    )
    raise SystemExit(result.returncode)
