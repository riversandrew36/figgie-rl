"""Training metadata saved beside model artifacts."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

import pytest
import yaml

from figgie_rl.train.metadata import (
    CHECKPOINT_SELECTION_RULE,
    build_training_metadata,
    metadata_path_for,
    resolve_training_settings,
    resolve_test_settings,
    write_model_metadata,
)
from figgie_rl.train.train_ppo import main


def _config(root: Path) -> dict:
    return {
        "run_name": "metadata_smoke",
        "seed": 3,
        "env": {
            "max_steps": 2,
            "drift_std": 0.0,
            "external_order_flow_prob": 0.0,
            "external_fill_prob": 0.0,
        },
        "train": {
            "total_timesteps": 16,
            "n_envs": 1,
            "learning_rate": 0.0003,
            "n_steps": 8,
            "batch_size": 8,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_range": 0.2,
            "ent_coef": 0.0,
            "vf_coef": 0.5,
            "eval_freq": 8,
            "n_eval_episodes": 1,
            "deterministic_eval": True,
            "validation_seed": 9001,
        },
        "paths": {"root_artifacts": str(root / "artifacts")},
    }


def test_metadata_schema_and_sidecar_path(tmp_path: Path) -> None:
    config = _config(tmp_path)
    settings = resolve_training_settings(config["train"], seed=3)
    context = build_training_metadata(
        config_path=str(tmp_path / "train.yaml"),
        config=config,
        observation_shape=(31,),
        seeds={
            "training_seed": 3,
            "model_seed": 3,
            "vector_env_seeds": [3],
            "validation_seed": 9001,
            "validation_episode_seeds": [9001],
        },
        training_settings=settings,
    )
    assert context["observation_shape"] == [31]
    assert context["python"]["version"] == platform.python_version()
    assert set(context["dependencies"]) >= {
        "figgie-rl",
        "gymnasium",
        "numpy",
        "PyYAML",
        "stable-baselines3",
        "torch",
    }
    assert isinstance(context["dependencies"]["torch"], str)
    assert context["resolved_config"]["env"]["max_steps"] == 2
    assert context["resolved_config"]["env"]["starting_cash"] == 350.0
    assert context["training_settings"]["validation_seed"] == 9001
    assert context["seeds"]["vector_env_seeds"] == [3]

    stem = tmp_path / "best_model" / "best_model"
    selection = {
        "timesteps": 8,
        "mean_final_bankroll": 360.0,
        "mean_profit": 10.0,
        "win_rate": 1.0,
        "mean_rank": 1.0,
        "episodes": 1,
        "validation_seed": 9001,
        "deterministic": True,
        "selection_rule": CHECKPOINT_SELECTION_RULE,
    }
    written = write_model_metadata(
        stem,
        role="best_model",
        context=context,
        checkpoint_selection=selection,
    )
    assert written == metadata_path_for(stem)
    assert written.name == "best_model.metadata.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["artifact"] == {
        "role": "best_model",
        "filename": "best_model.zip",
        "path": str((stem.parent / "best_model.zip").resolve()),
    }
    assert payload["checkpoint_selection"]["mean_profit"] == 10.0
    assert payload["checkpoint_selection"]["selection_rule"] == CHECKPOINT_SELECTION_RULE


def test_train_writes_metadata_beside_both_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    config_path = tmp_path / "train.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["figgie-train", "--config", str(config_path)])
    main()

    run_dir = tmp_path / "artifacts" / "metadata_smoke"
    best_meta = json.loads(
        (run_dir / "best_model" / "best_model.metadata.json").read_text(encoding="utf-8")
    )
    final_meta = json.loads(
        (run_dir / "models" / "final_model.metadata.json").read_text(encoding="utf-8")
    )
    assert (run_dir / "best_model" / "best_model.zip").is_file()
    assert (run_dir / "models" / "final_model.zip").is_file()

    for payload, role in ((best_meta, "best_model"), (final_meta, "final_model")):
        assert payload["artifact"]["role"] == role
        assert payload["artifact"]["filename"] == f"{role}.zip"
        assert payload["config_path"] == str(config_path.resolve())
        assert payload["observation_shape"] == [31]
        assert payload["seeds"]["training_seed"] == 3
        assert payload["seeds"]["model_seed"] == 3
        assert payload["seeds"]["vector_env_seeds"] == [3]
        assert payload["seeds"]["validation_seed"] == 9001
        assert payload["seeds"]["validation_episode_seeds"] == [9001]
        assert payload["training_settings"]["total_timesteps"] == 16
        assert payload["training_settings"]["policy"] == "MlpPolicy"
        assert payload["resolved_config"]["run_name"] == "metadata_smoke"
        assert payload["resolved_config"]["env"]["max_steps"] == 2
        assert payload["python"]["version"] == platform.python_version()
        assert isinstance(payload["dependencies"]["numpy"], str)
        selection = payload["checkpoint_selection"]
        assert selection["validation_seed"] == 9001
        assert selection["episodes"] == 1
        assert selection["selection_rule"] == CHECKPOINT_SELECTION_RULE
        assert selection["timesteps"] >= 8
        for key in ("mean_final_bankroll", "mean_profit", "win_rate", "mean_rank"):
            assert isinstance(selection[key], float)

    assert best_meta["checkpoint_selection"] == final_meta["checkpoint_selection"]
    result = final_meta["training_result"]
    assert result["total_timesteps_requested"] == 16
    assert result["timesteps_completed"] >= 16
    assert result["best_checkpoint_timesteps"] == best_meta["checkpoint_selection"]["timesteps"]


def test_reserved_test_range_rejects_validation_overlap() -> None:
    config = {
        "train": {"validation_seed": 50007, "n_eval_episodes": 200},
        "evaluation": {"test_seed": 700000, "test_episodes": 1000},
    }
    assert resolve_test_settings(config) == (700000, 1000)
    config["evaluation"]["test_seed"] = 50206
    with pytest.raises(ValueError, match="overlap"):
        resolve_test_settings(config)
    config["evaluation"]["test_seed"] = 50207
    assert resolve_test_settings(config) == (50207, 1000)
    config["evaluation"]["test_episodes"] = 0
    with pytest.raises(ValueError, match="episodes"):
        resolve_test_settings(config)
