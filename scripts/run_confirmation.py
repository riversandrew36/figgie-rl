"""Matched three-seed historical-opponent-pool PPO comparison."""

from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC_PATH = ROOT / "configs/confirmation.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text())
OUT = ROOT / "results" / SPEC["study_id"]
ARMS = ("fixed", "self_play")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2) + "\n")


def load(p):
    return json.loads(Path(p).read_text())


def name(arm, seed):
    return f"{arm}_seed_{seed}"


def artifact(arm, seed):
    return ROOT / "artifacts" / f"{SPEC['study_id']}_{name(arm, seed)}"


def cfgpath(arm, seed, shifted=False):
    return OUT / "configs" / f"{name(arm, seed)}{'_shifted' if shifted else ''}.yaml"


def event(s):
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"), s, flush=True)


def hashes():
    ps = [
        SPEC_PATH,
        ROOT / "docs/CONFIRMATION_PROTOCOL.md",
        Path(__file__),
        ROOT / "figgie_rl/envs/simple_figgie_env.py",
        ROOT / "figgie_rl/train/self_play.py",
        ROOT / "figgie_rl/train/train_ppo.py",
        ROOT / "figgie_rl/train/evaluate.py",
        *map(lambda x: ROOT / x, SPEC["historical_checkpoints"]),
    ]
    return {str(p.relative_to(ROOT)): sha(p) for p in ps}


def childenv():
    return dict(
        os.environ,
        PYTHONPATH=str(ROOT),
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        MPLCONFIGDIR="/tmp/figgie-mpl",
        XDG_CACHE_HOME="/tmp/figgie-cache",
    )


def makecfg(arm, seed, shift=False):
    env = (
        deepcopy(SPEC["env"])
        | SPEC["reward"]
        | {
            "opponent_difficulties": SPEC["shifted_opponents"]
            if shift
            else SPEC["familiar_opponents"]
        }
    )
    return {
        "run_name": f"{SPEC['study_id']}_{name(arm, seed)}",
        "seed": seed,
        "env": env,
        "train": deepcopy(SPEC["train"])
        | {
            "total_timesteps": SPEC["training_timesteps"],
            "eval_freq": SPEC["self_play_chunk_timesteps"],
            "validation_seed": SPEC["validation"]["seed"],
            "n_eval_episodes": SPEC["validation"]["episodes"],
        },
        "evaluation": {
            "test_seed": SPEC["final"]["seed"],
            "test_episodes": SPEC["final"]["episodes"],
        },
        "paths": {"root_artifacts": "artifacts"},
    }


def prepare():
    h = hashes()
    m = OUT / "manifest.json"
    if m.exists():
        assert load(m)["source_hashes"] == h, (
            "source/config changed; choose a new study id"
        )
        return
    for a in ARMS:
        for seed in SPEC["training_seeds"]:
            c = makecfg(a, seed)
            for shift in (False, True):
                d = deepcopy(c)
                if shift:
                    d["env"]["opponent_difficulties"] = SPEC["shifted_opponents"]
                cfgpath(a, seed, shift).parent.mkdir(parents=True, exist_ok=True)
                cfgpath(a, seed, shift).write_text(yaml.safe_dump(d, sort_keys=False))
    save(
        m,
        {
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "source_hashes": h,
            "specification": SPEC,
            "python": sys.version,
            "compute": {"device": "cpu", "workers": 2, "threads_per_worker": 1},
            "dependencies": __import__(
                "figgie_rl.train.metadata", fromlist=["dependency_versions"]
            ).dependency_versions(),
        },
    )


def worker(args, log):
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    with (OUT / "logs" / log).open("w") as f:
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *args],
            cwd=ROOT,
            env=childenv(),
            stdout=f,
            stderr=subprocess.STDOUT,
            check=True,
        )


def train(a, s):
    import numpy as np
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    from figgie_rl.envs.simple_figgie_env import EnvConfig
    from figgie_rl.train.self_play import _choose_pool, _make_env
    from figgie_rl.train.metadata import build_training_metadata, write_model_metadata

    marker = OUT / "completed" / f"{name(a, s)}.json"
    if marker.exists():
        return
    dest = artifact(a, s)
    if dest.exists():
        raise RuntimeError(f"Partial run preserved at {dest}")
    cfg = makecfg(a, s)
    env_cfg = cfg["env"]
    t = cfg["train"]
    historical = list(SPEC["historical_checkpoints"])
    sampling = np.random.default_rng(s)
    model = None
    schedule = []
    for stage in range(SPEC["self_play_iterations"]):
        numpy_state = np.random.get_state()
        torch_state = torch.random.get_rng_state()
        if a == "self_play":
            pool = _choose_pool(
                historical, sampling, 4, EnvConfig(**env_cfg), checkpoint_pool_size=2
            )
        else:
            pool = _choose_pool([], sampling, 4, EnvConfig(**env_cfg))
        np.random.set_state(numpy_state)
        torch.random.set_rng_state(torch_state)
        schedule.append(
            [
                getattr(p, "config", None).__class__.__name__
                if not hasattr(p, "model")
                else "frozen_PPO"
                for p in pool
            ]
        )
        vec = DummyVecEnv(
            [
                lambda rank=rank: _make_env(env_cfg, s + 1000 * stage + rank, pool)
                for rank in range(t["n_envs"])
            ]
        )
        if model is None:
            model = PPO(
                "MlpPolicy",
                vec,
                learning_rate=t["learning_rate"],
                n_steps=t["n_steps"],
                batch_size=t["batch_size"],
                gamma=t["gamma"],
                gae_lambda=t["gae_lambda"],
                clip_range=t["clip_range"],
                ent_coef=t["ent_coef"],
                vf_coef=t["vf_coef"],
                seed=s,
                device="cpu",
                verbose=0,
            )
        else:
            model.set_env(vec)
        model.learn(
            total_timesteps=SPEC["self_play_chunk_timesteps"], reset_num_timesteps=False
        )
        stem = dest / "self_play" / "checkpoints" / f"iter_{stage:03d}"
        stem.parent.mkdir(parents=True, exist_ok=True)
        model.save(stem)
        context = build_training_metadata(
            config_path=str(cfgpath(a, s)),
            config=cfg,
            observation_shape=vec.observation_space.shape,
            seeds={
                "model_seed": s,
                "vector_env_seeds": [s + 1000 * stage + r for r in range(t["n_envs"])],
            },
            training_settings=t,
        )
        write_model_metadata(
            stem,
            role="matched_stage",
            context=context,
            checkpoint_selection=None,
            extra={"stage": stage, "timesteps": model.num_timesteps},
        )
        historical.append(str(stem) + ".zip")
        vec.close()
        event(f"{name(a, s)} stage {stage + 1}/6 complete")
    final = dest / "models" / "final_model"
    final.parent.mkdir(parents=True, exist_ok=True)
    model.save(final)
    save(
        marker,
        {
            "timesteps": model.num_timesteps,
            "model": str(final) + ".zip",
            "sha256": sha(Path(str(final) + ".zip")),
            "schedule": schedule,
        },
    )


def choose(a, s):
    from figgie_rl.train.evaluate import run_evaluation

    n = name(a, s)
    p = OUT / "selection" / f"{n}.json"
    if p.exists():
        return
    if False:
        model = artifact(a, s) / "best_model/best_model.zip"
        m = load(model.with_suffix(".metadata.json"))["checkpoint_selection"]
        save(p, {"model": str(model), "sha256": sha(model), "selection": m})
    else:
        cand = []
        for i in range(SPEC["self_play_iterations"]):
            model = artifact(a, s) / f"self_play/checkpoints/iter_{i:03}.zip"
            r = run_evaluation(
                model_path=str(model),
                config_path=str(cfgpath(a, s)),
                episodes=SPEC["validation"]["episodes"],
                seed=SPEC["validation"]["seed"],
                benchmark=False,
            )
            r["configuration"]["evaluation_split"] = "validation"
            save(OUT / "validation" / f"{n}_iter_{i:03d}.json", r)
            row = r["aggregates"][0]
            cand.append(
                {
                    "model": str(model),
                    "sha256": sha(model),
                    "selection": {
                        "timesteps": (i + 1) * SPEC["self_play_chunk_timesteps"],
                        "mean_final_bankroll": row["mean_bankroll"],
                        "mean_profit": row["mean_profit"],
                        "win_rate": row["win_rate"],
                        "mean_rank": row["mean_rank"],
                    },
                }
            )
        save(
            p,
            max(
                cand,
                key=lambda x: (
                    x["selection"]["mean_final_bankroll"],
                    x["selection"]["win_rate"],
                    -x["selection"]["mean_rank"],
                ),
            ),
        )
    event(f"selected {n}")


def freeze():
    p = OUT / "frozen_selection.json"
    if p.exists():
        f = load(p)
        assert f["source_hashes"] == hashes()
        return f
    models = {
        name(a, s): load(OUT / "selection" / f"{name(a, s)}.json")
        for a in ARMS
        for s in SPEC["training_seeds"]
    }
    f = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_hashes": hashes(),
        "models": models,
        "specification": SPEC,
    }
    save(p, f)
    event("FROZEN checkpoints before final evaluation")
    return f


def verify():
    f = load(OUT / "frozen_selection.json")
    assert f["source_hashes"] == hashes()
    for m in f["models"].values():
        assert sha(m["model"]) == m["sha256"]
    return f


def evaluate(a, s, split, shift=False, benchmark=False):
    from figgie_rl.train.evaluate import run_evaluation

    n = name(a, s)
    suffix = "shifted" if shift else "familiar"
    p = OUT / split / f"{n}_{suffix}.json"
    if p.exists():
        return
    if split == "final":
        verify()
    choice = load(OUT / "selection" / f"{n}.json")
    kw = (
        {"episodes": None, "seed": None, "test": True}
        if split == "final"
        else {
            "episodes": SPEC["exploratory"]["episodes"],
            "seed": SPEC["exploratory"]["seed"],
        }
    )
    r = run_evaluation(
        model_path=choice["model"],
        config_path=str(cfgpath(a, s, shift)),
        benchmark=benchmark,
        **kw,
    )
    save(p, r)
    event(f"{split}/{n}/{suffix}")


def merge_nonref(p, base):
    from scripts.run_rl_study import merge_baselines

    r = load(p)
    if not r["benchmark"]:
        save(
            p,
            merge_baselines(
                r,
                base,
                str(
                    p.parent / base["model_path"]
                    if False
                    else "cached per-lineup baseline report"
                ),
            ),
        )


def suite(split, shift=False):
    jobs = [(a, s) for a in ARMS for s in SPEC["training_seeds"]]

    # workers validate compatible schemas; reuse model-independent baseline results per lineup.
    def one(pair):
        i, (a, s) = pair
        worker(
            [
                "--job",
                "evaluate",
                "--arm",
                a,
                "--seed",
                str(s),
                "--split",
                split,
                *(["--shift"] if shift else []),
                *(["--benchmark"] if i == 0 else []),
            ],
            f"{split}_{name(a, s)}_{'shift' if shift else 'fam'}.log",
        )

    with ThreadPoolExecutor(max_workers=SPEC["workers"]) as ex:
        list(ex.map(one, enumerate(jobs)))
    ref = load(
        OUT / split / f"{name(*jobs[0])}_{'shifted' if shift else 'familiar'}.json"
    )
    for a, s in jobs[1:]:
        p = OUT / split / f"{name(a, s)}_{'shifted' if shift else 'familiar'}.json"
        if not load(p)["benchmark"]:
            from scripts.run_rl_study import merge_baselines

            save(
                p,
                merge_baselines(
                    load(p),
                    ref,
                    str(
                        OUT
                        / split
                        / f"{name(*jobs[0])}_{'shifted' if shift else 'familiar'}.json"
                    ),
                ),
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", choices=["train", "select", "evaluate"])
    ap.add_argument("--arm", choices=ARMS)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--split", choices=["exploratory", "final"])
    ap.add_argument("--shift", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    args = ap.parse_args()
    if args.job:
        import torch

        torch.set_num_threads(1)
        {
            "train": lambda: train(args.arm, args.seed),
            "select": lambda: choose(args.arm, args.seed),
            "evaluate": lambda: evaluate(
                args.arm, args.seed, args.split, args.shift, args.benchmark
            ),
        }[args.job]()
        return
    prepare()
    with ThreadPoolExecutor(max_workers=SPEC["workers"]) as ex:
        list(
            ex.map(
                lambda q: worker(
                    ["--job", "train", "--arm", q[0], "--seed", str(q[1])],
                    f"{name(*q)}_train.log",
                ),
                [(a, s) for a in ARMS for s in SPEC["training_seeds"]],
            )
        )
    with ThreadPoolExecutor(max_workers=SPEC["workers"]) as ex:
        list(
            ex.map(
                lambda q: worker(
                    ["--job", "select", "--arm", q[0], "--seed", str(q[1])],
                    f"{name(*q)}_select.log",
                ),
                [(a, s) for a in ARMS for s in SPEC["training_seeds"]],
            )
        )
    suite("exploratory")
    freeze()
    suite("final")
    suite("final", True)
    event("three-seed matched comparison complete")


if __name__ == "__main__":
    main()
