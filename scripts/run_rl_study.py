"""Reproducible, validation-selected PPO/self-play study; results stay local."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC_PATH = ROOT / "configs/rl_study.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text())
OUTPUT = ROOT / "results" / SPEC["study_id"]
ARMS = ("fixed", "self_play")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def event(message: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {message}", flush=True)


def check_design(spec: dict) -> None:
    rollout = spec["train"]["n_envs"] * spec["train"]["n_steps"]
    assert spec["training_timesteps"] % rollout == 0
    assert spec["self_play_chunk_timesteps"] % rollout == 0
    assert spec["self_play_iterations"] * spec["self_play_chunk_timesteps"] == spec["training_timesteps"]
    assert len(set(spec["training_seeds"])) == len(spec["training_seeds"])
    ranges = [set(range(spec[key]["seed"], spec[key]["seed"] + spec[key]["episodes"]))
              for key in ("validation", "exploratory", "final")]
    assert not any(left & right for i, left in enumerate(ranges) for right in ranges[i+1:])


def source_hashes() -> dict[str, str]:
    paths = [SPEC_PATH, ROOT / "docs/RL_STUDY_PROTOCOL.md", Path(__file__),
             ROOT / SPEC["standard_config"], *sorted((ROOT / "figgie_rl").rglob("*.py"))]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def run_id(arm: str, seed: int) -> str:
    return f"{arm}_seed_{seed}"


def config_path(name: str, shifted: bool = False) -> Path:
    return OUTPUT / "configs" / f"{name}{'_shifted' if shifted else ''}.yaml"


def config_for(arm: str, seed: int, spec: dict) -> dict:
    return {
        "run_name": f"{spec['study_id']}_{run_id(arm, seed)}", "seed": seed,
        "env": deepcopy(spec["env"]) | {"opponent_difficulties": spec["familiar_opponents"]},
        "train": deepcopy(spec["train"]) | {
            "total_timesteps": spec["training_timesteps"],
            "eval_freq": spec["self_play_chunk_timesteps"],
            "n_eval_episodes": spec["validation"]["episodes"],
            "validation_seed": spec["validation"]["seed"],
        },
        "evaluation": {"test_seed": spec["final"]["seed"], "test_episodes": spec["final"]["episodes"]},
        "paths": {"root_artifacts": "artifacts"},
    }


def artifact_dir(name: str) -> Path:
    return ROOT / "artifacts" / f"{SPEC['study_id']}_{name}"


def prepare() -> None:
    from figgie_rl.train.metadata import dependency_versions
    check_design(SPEC)
    current = source_hashes()
    manifest = OUTPUT / "manifest.json"
    if manifest.exists():
        if load(manifest)["source_hashes"] != current:
            raise RuntimeError("Study source/config changed; use a new study ID instead of mixing runs")
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for arm in ARMS:
        for seed in SPEC["training_seeds"]:
            name = run_id(arm, seed)
            cfg = config_for(arm, seed, SPEC)
            for shifted in (False, True):
                target = deepcopy(cfg)
                if shifted:
                    target["env"]["opponent_difficulties"] = SPEC["shifted_opponents"]
                path = config_path(name, shifted)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(yaml.safe_dump(target, sort_keys=False))
    save(manifest, {
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(), "specification": SPEC,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_hashes": current, "dependencies": dependency_versions(), "python": sys.version,
        "compute": {"device": "cpu", "torch_threads": 1, "workers": SPEC["workers"]},
    })
    event("Prepared protocol, generated configs, and immutable source manifest")


def child_env() -> dict:
    return dict(os.environ) | {
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "PYTHONPATH": str(ROOT),
        "MPLCONFIGDIR": "/tmp/figgie-mpl", "XDG_CACHE_HOME": "/tmp/figgie-cache",
    }


def train(arm: str, seed: int) -> None:
    name = run_id(arm, seed)
    marker = OUTPUT / "completed" / f"{name}.json"
    if marker.exists():
        event(f"Reuse completed training: {name}")
        return
    if artifact_dir(name).exists():
        raise RuntimeError(f"Partial or unrecorded training exists: {artifact_dir(name)}")
    module = "self_play" if arm == "self_play" else "train_ppo"
    command = [sys.executable, "-m", f"figgie_rl.train.{module}", "--config", str(config_path(name))]
    if arm == "self_play":
        command += ["--iterations", str(SPEC["self_play_iterations"]), "--chunk-timesteps",
                    str(SPEC["self_play_chunk_timesteps"]), "--seed", str(seed)]
    log = OUTPUT / "logs" / f"{name}_train.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    event(f"Start training {name}: {SPEC['training_timesteps']:,} steps")
    with log.open("w") as handle:
        subprocess.run(command, cwd=ROOT, env=child_env(), stdout=handle, stderr=subprocess.STDOUT, check=True)
    final = artifact_dir(name) / ("self_play/final_self_play_model.zip" if arm == "self_play" else "models/final_model.zip")
    metadata = load(final.with_suffix(".metadata.json"))
    completed = metadata["self_play"]["timesteps"] if arm == "self_play" else metadata["training_result"]["timesteps_completed"]
    assert completed == SPEC["training_timesteps"], (name, completed)
    save(marker, {"command": command, "final_model": str(final), "sha256": sha(final), "timesteps": completed})
    event(f"Completed training {name}")


def select(arm: str, seed: int) -> None:
    from figgie_rl.train.evaluate import run_evaluation
    name = run_id(arm, seed)
    target = OUTPUT / "selection" / f"{name}.json"
    if target.exists():
        return
    if arm == "fixed":
        model = artifact_dir(name) / "best_model/best_model.zip"
        meta = load(model.with_suffix(".metadata.json"))
        choice = meta["checkpoint_selection"]
        save(target, {"model": str(model), "model_sha256": sha(model), "selection": choice})
    else:
        candidates = []
        for iteration in range(SPEC["self_play_iterations"]):
            model = artifact_dir(name) / f"self_play/checkpoints/iter_{iteration:03d}.zip"
            report_path = OUTPUT / "validation" / f"{name}_iter_{iteration:03d}.json"
            if report_path.exists():
                report = load(report_path)
            else:
                report = run_evaluation(model_path=str(model), config_path=str(config_path(name)),
                                        episodes=SPEC["validation"]["episodes"], seed=SPEC["validation"]["seed"],
                                        benchmark=False)
                report["configuration"]["evaluation_split"] = "validation"
                save(report_path, report)
            row = report["aggregates"][0]
            candidates.append({"model": str(model), "model_sha256": sha(model), "selection": {
                "timesteps": (iteration+1)*SPEC["self_play_chunk_timesteps"],
                "mean_final_bankroll": row["mean_bankroll"], "mean_profit": row["mean_profit"],
                "win_rate": row["win_rate"], "mean_rank": row["mean_rank"],
                "validation_seed": SPEC["validation"]["seed"], "episodes": SPEC["validation"]["episodes"],
            }})
        save(target, choose_checkpoint(candidates))
    event(f"Validation-selected {name}")


def choose_checkpoint(candidates: list[dict]) -> dict:
    return max(candidates, key=lambda item: (item["selection"]["mean_final_bankroll"],
                                            item["selection"]["win_rate"], -item["selection"]["mean_rank"]))


def merge_baselines(report: dict, benchmark: dict, provenance: str) -> dict:
    from figgie_rl.train.evaluate import _paired_rows
    assert report["seeds"] == benchmark["seeds"]
    assert report["configuration"]["env"] == benchmark["configuration"]["env"]
    merged = deepcopy(report)
    merged["benchmark"] = True
    merged["baseline_cache_source"] = provenance
    merged["policies"] = benchmark["policies"]
    merged["per_episode"] += [row for row in benchmark["per_episode"] if row["policy"] != "PPO"]
    merged["aggregates"] += [row for row in benchmark["aggregates"] if row["policy"] != "PPO"]
    profits = {policy: {"profits": [row["profit"] for row in merged["per_episode"] if row["policy"] == policy]}
               for policy in merged["policies"]}
    merged["paired_profit_differences"] = _paired_rows("PPO", profits)
    return merged


def verify_frozen() -> dict:
    frozen = load(OUTPUT / "frozen_selection.json")
    assert frozen["source_hashes"] == source_hashes(), "Source changed after freezing"
    for choice in frozen["models"].values():
        assert sha(Path(choice["model"])) == choice["model_sha256"], "Checkpoint changed after freezing"
    return frozen


def evaluate(arm: str, seed: int, split: str, shifted: bool, benchmark: bool) -> None:
    from figgie_rl.train.evaluate import run_evaluation
    name = run_id(arm, seed)
    suffix = "shifted" if shifted else "familiar"
    path = OUTPUT / split / f"{name}_{suffix}.json"
    if path.exists():
        return
    if split == "final":
        verify_frozen()
    choice = load(OUTPUT / "selection" / f"{name}.json")
    args = {"episodes": None, "seed": None, "test": True} if split == "final" else {
        "episodes": SPEC["exploratory"]["episodes"], "seed": SPEC["exploratory"]["seed"]}
    report = run_evaluation(model_path=choice["model"], config_path=str(config_path(name, shifted)),
                            benchmark=benchmark, **args)
    save(path, report)
    event(f"Evaluated {split}/{name}/{suffix}")


def worker(arguments: list[str]) -> None:
    subprocess.run([sys.executable, str(Path(__file__).resolve()), *arguments], cwd=ROOT,
                   env=child_env(), check=True)


def parallel(jobs: list[list[str]]) -> None:
    with ThreadPoolExecutor(max_workers=SPEC["workers"]) as pool:
        list(pool.map(worker, jobs))


def suite(split: str, shifted: bool) -> None:
    names = [(arm, seed) for arm in ARMS for seed in SPEC["training_seeds"]]
    parallel([["--job", "evaluate", "--arm", arm, "--seed", str(seed), "--split", split,
               *(["--shifted"] if shifted else []), *(["--benchmark"] if i == 0 else [])]
              for i, (arm, seed) in enumerate(names)])
    suffix = "shifted" if shifted else "familiar"
    reference = OUTPUT / split / f"{run_id(*names[0])}_{suffix}.json"
    base = load(reference)
    for arm, seed in names[1:]:
        path = OUTPUT / split / f"{run_id(arm, seed)}_{suffix}.json"
        report = load(path)
        if not report["benchmark"]:
            save(path, merge_baselines(report, base, str(reference)))


def freeze() -> None:
    if (OUTPUT / "frozen_selection.json").exists():
        verify_frozen()
        return
    models = {run_id(arm, seed): load(OUTPUT / "selection" / f"{run_id(arm, seed)}.json")
              for arm in ARMS for seed in SPEC["training_seeds"]}
    standard = ROOT / "artifacts/ppo_goal_belief_v2/best_model/best_model.zip"
    standard_final = ROOT / "artifacts/ppo_goal_belief_v2/models/final_model.metadata.json"
    assert standard_final.exists(), "The original standard run must finish first"
    models["standard"] = {"model": str(standard), "model_sha256": sha(standard),
                          "selection": load(standard.with_suffix(".metadata.json"))["checkpoint_selection"]}
    save(OUTPUT / "frozen_selection.json", {"frozen_at_utc": datetime.now(timezone.utc).isoformat(),
         "source_hashes": source_hashes(), "models": models, "specification": SPEC})
    event("FROZEN: all selected checkpoints and design recorded before any final test")


def standard_test() -> None:
    from figgie_rl.train.evaluate import run_evaluation
    path = OUTPUT / "final/standard_exogenous.json"
    if path.exists():
        return
    frozen = verify_frozen()
    report = run_evaluation(model_path=frozen["models"]["standard"]["model"],
                            config_path=str(ROOT / SPEC["standard_config"]), episodes=None,
                            seed=None, benchmark=True, test=True)
    save(path, report)
    event("Completed original outside-book reserved final benchmark")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", choices=["train", "select", "evaluate", "standard"])
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--split", choices=["exploratory", "final"], default="exploratory")
    parser.add_argument("--shifted", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    if args.job:
        import torch
        torch.set_num_threads(1)
        if args.job == "train":
            train(args.arm, args.seed)
        elif args.job == "select":
            select(args.arm, args.seed)
        elif args.job == "standard":
            standard_test()
        else:
            evaluate(args.arm, args.seed, args.split, args.shifted, args.benchmark)
        return
    prepare()
    for job in ("train", "select"):
        parallel([["--job", job, "--arm", arm, "--seed", str(seed)]
                  for arm in ARMS for seed in SPEC["training_seeds"]])
    suite("exploratory", False)
    freeze()
    suite("final", False)
    suite("final", True)
    worker(["--job", "standard"])
    event("STUDY COMPLETE: all held-out reports saved; no post-test tuning")


if __name__ == "__main__":
    main()
