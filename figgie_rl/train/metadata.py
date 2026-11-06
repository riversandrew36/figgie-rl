"""Sidecar metadata written next to training model artifacts."""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from figgie_rl.envs.simple_figgie_env import EnvConfig

CHECKPOINT_SELECTION_RULE = (
    "lexicographic: higher mean_final_bankroll, then higher win_rate, then lower mean_rank"
)

TRACKED_PACKAGES = (
    "figgie-rl",
    "gymnasium",
    "numpy",
    "PyYAML",
    "stable-baselines3",
    "torch",
    "tqdm",
    "rich",
)


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bool) or value is None or isinstance(value, (str, int, float)):
        return value
    item = getattr(value, "item", None)
    if callable(item):
        return json_ready(item())
    return str(value)


def dependency_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in TRACKED_PACKAGES:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    return versions


def resolve_training_settings(train_cfg: dict[str, Any], seed: int) -> dict[str, Any]:
    """Coerce the YAML training block into the values passed to PPO."""
    return {
        "policy": "MlpPolicy",
        "total_timesteps": int(train_cfg["total_timesteps"]),
        "n_envs": int(train_cfg["n_envs"]),
        "learning_rate": float(train_cfg["learning_rate"]),
        "n_steps": int(train_cfg["n_steps"]),
        "batch_size": int(train_cfg["batch_size"]),
        "gamma": float(train_cfg["gamma"]),
        "gae_lambda": float(train_cfg["gae_lambda"]),
        "clip_range": float(train_cfg["clip_range"]),
        "ent_coef": float(train_cfg["ent_coef"]),
        "vf_coef": float(train_cfg["vf_coef"]),
        "eval_freq": int(train_cfg["eval_freq"]),
        "n_eval_episodes": int(train_cfg["n_eval_episodes"]),
        "deterministic_eval": bool(train_cfg.get("deterministic_eval", True)),
        "validation_seed": int(train_cfg.get("validation_seed", seed + 10000)),
    }


def resolve_test_settings(config: dict[str, Any]) -> tuple[int, int]:
    """Resolve the reserved final-test range and reject validation overlap."""
    plan = config.get("evaluation", {})
    if "test_seed" not in plan or "test_episodes" not in plan:
        raise ValueError("--test requires evaluation.test_seed and evaluation.test_episodes in the config")
    seed, episodes = int(plan["test_seed"]), int(plan["test_episodes"])
    if seed < 0 or episodes <= 0:
        raise ValueError("Test seed must be nonnegative and test episodes must be > 0")
    train = config.get("train", {})
    validation_seed = int(train.get("validation_seed", int(config.get("seed", 7)) + 10000))
    validation_episodes = int(train.get("n_eval_episodes", 0))
    if max(seed, validation_seed) < min(seed + episodes, validation_seed + validation_episodes):
        raise ValueError("Final-test seeds overlap checkpoint-validation seeds")
    return seed, episodes


def build_training_metadata(
    *,
    config_path: str,
    config: dict[str, Any],
    observation_shape: tuple[int, ...] | list[int],
    seeds: dict[str, Any],
    training_settings: dict[str, Any],
) -> dict[str, Any]:
    resolved_env = EnvConfig(**dict(config["env"]))
    return {
        "config_path": str(Path(config_path).resolve()),
        "resolved_config": {
            "run_name": config.get("run_name", "ppo_simple"),
            "seed": int(config.get("seed", 7)),
            "env": json_ready(asdict(resolved_env)),
            "train": json_ready(dict(config["train"])),
            "paths": json_ready(dict(config.get("paths", {}))),
            "evaluation": json_ready(dict(config.get("evaluation", {}))),
        },
        "seeds": json_ready(seeds),
        "python": {
            "version": platform.python_version(),
            "version_info": [int(part) for part in sys.version_info[:3]],
            "implementation": platform.python_implementation(),
            "full": sys.version,
        },
        "dependencies": dependency_versions(),
        "observation_shape": [int(dim) for dim in observation_shape],
        "training_settings": json_ready(training_settings),
    }


def metadata_path_for(model_stem: Path) -> Path:
    return model_stem.parent / f"{model_stem.name}.metadata.json"


def write_model_metadata(
    model_stem: Path,
    *,
    role: str,
    context: dict[str, Any],
    checkpoint_selection: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        "artifact": {
            "role": role,
            "filename": f"{model_stem.name}.zip",
            "path": str((model_stem.parent / f"{model_stem.name}.zip").resolve()),
        },
        "config_path": context["config_path"],
        "resolved_config": context["resolved_config"],
        "seeds": context["seeds"],
        "python": context["python"],
        "dependencies": context["dependencies"],
        "observation_shape": context["observation_shape"],
        "training_settings": context["training_settings"],
        "checkpoint_selection": checkpoint_selection,
    }
    if extra:
        payload.update(json_ready(extra))
    path = metadata_path_for(model_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
