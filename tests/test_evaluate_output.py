"""Output formats for the evaluation CLI."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest
import yaml
from stable_baselines3 import PPO

from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.train.evaluate import (
    AGGREGATE_FIELDS,
    EPISODE_FIELDS,
    PAIRED_FIELDS,
    main,
    print_report,
    run_evaluation,
    write_evaluation_report,
)


def _sample_report() -> dict:
    return {
        "model_path": "models/policy.zip",
        "model_path_resolved": "/tmp/models/policy.zip",
        "config_path": "/tmp/configs/ppo_simple.yaml",
        "benchmark": True,
        "episodes": 2,
        "base_seed": 101,
        "seeds": [101, 102],
        "agent_rng_seeds": [500101, 500102],
        "policies": ["PPO", "Hold"],
        "configuration": {
            "starting_cash": 350.0,
            "profit_definition": "final_bankroll - starting_cash",
            "paired_reference": "PPO",
            "ci_method": {
                "aggregate_profit": "1.96 * population_stdev / sqrt(n)",
                "paired_difference": "1.96 * sample_stdev / sqrt(n)",
            },
            "env": {"max_steps": 2, "starting_cash": 350.0},
            "loaded_config": {"run_name": "sample", "env": {"max_steps": 2}},
        },
        "per_episode": [
            {
                "episode": 0,
                "seed": 101,
                "agent_rng_seed": 500101,
                "policy": "PPO",
                "profit": 5.0,
                "win": True,
                "tie": False,
                "rank": 1,
                "bankroll": 355.0,
                "drawdown": 1.0,
                "inventory_risk": 0.5,
                "quote_fill_rate": 0.25,
                "spread_capture": 0.0,
            },
            {
                "episode": 1,
                "seed": 102,
                "agent_rng_seed": 500102,
                "policy": "PPO",
                "profit": 1.0,
                "win": False,
                "tie": False,
                "rank": 2,
                "bankroll": 351.0,
                "drawdown": 0.0,
                "inventory_risk": 0.0,
                "quote_fill_rate": 0.0,
                "spread_capture": 1.5,
            },
            {
                "episode": 0,
                "seed": 101,
                "agent_rng_seed": 500101,
                "policy": "Hold",
                "profit": 2.0,
                "win": False,
                "tie": True,
                "rank": 2,
                "bankroll": 352.0,
                "drawdown": 0.0,
                "inventory_risk": 0.0,
                "quote_fill_rate": 0.0,
                "spread_capture": 0.0,
            },
            {
                "episode": 1,
                "seed": 102,
                "agent_rng_seed": 500102,
                "policy": "Hold",
                "profit": 4.0,
                "win": True,
                "tie": False,
                "rank": 1,
                "bankroll": 354.0,
                "drawdown": 0.0,
                "inventory_risk": 0.0,
                "quote_fill_rate": 0.0,
                "spread_capture": 0.0,
            },
        ],
        "aggregates": [
            {
                "policy": "PPO",
                "episodes": 2,
                "mean_profit": 3.0,
                "profit_ci95": 1.0,
                "win_rate": 0.5,
                "tie_rate": 0.0,
                "mean_rank": 1.5,
                "mean_bankroll": 353.0,
                "mean_drawdown": 0.5,
                "mean_inventory_risk": 0.25,
                "mean_quote_fill_rate": 0.125,
                "mean_spread_capture": 0.75,
            }
        ],
        "paired_profit_differences": [
            {
                "reference": "PPO",
                "other": "Hold",
                "episodes": 2,
                "mean_difference": 0.0,
                "ci95": 2.0,
                "beat_rate": 0.5,
            }
        ],
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_write_json_and_csv_reports(tmp_path: Path) -> None:
    report = _sample_report()
    json_path = tmp_path / "bench.json"
    written_json = write_evaluation_report(json_path, report)
    assert written_json == [json_path]
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["seeds"] == [101, 102]
    assert loaded["policies"] == ["PPO", "Hold"]
    assert loaded["configuration"]["loaded_config"]["run_name"] == "sample"
    assert loaded["paired_profit_differences"][0]["other"] == "Hold"
    assert loaded["per_episode"][0]["win"] is True

    csv_path = tmp_path / "bench.csv"
    episodes, aggregates, paired, meta = write_evaluation_report(csv_path, report)
    assert episodes == csv_path
    assert aggregates.name == "bench.aggregates.csv"
    assert paired.name == "bench.paired.csv"
    assert meta.name == "bench.meta.csv"

    episode_rows = _read_csv(episodes)
    assert list(episode_rows[0]) == list(EPISODE_FIELDS)
    assert len(episode_rows) == 4
    assert episode_rows[0]["policy"] == "PPO"
    assert episode_rows[0]["seed"] == "101"
    assert episode_rows[0]["win"] == "true"
    assert episode_rows[2]["tie"] == "true"

    aggregate_rows = _read_csv(aggregates)
    assert list(aggregate_rows[0]) == list(AGGREGATE_FIELDS)
    assert aggregate_rows[0]["policy"] == "PPO"
    assert float(aggregate_rows[0]["mean_profit"]) == 3.0

    paired_rows = _read_csv(paired)
    assert list(paired_rows[0]) == list(PAIRED_FIELDS)
    assert paired_rows[0]["reference"] == "PPO"
    assert paired_rows[0]["other"] == "Hold"
    assert float(paired_rows[0]["mean_difference"]) == loaded["paired_profit_differences"][0]["mean_difference"]

    meta_rows = {row["key"]: row["value"] for row in _read_csv(meta)}
    assert meta_rows["base_seed"] == "101"
    assert meta_rows["policies"] == "PPO;Hold"
    assert meta_rows["seeds"] == "101;102"
    assert meta_rows["benchmark"] == "true"
    configuration = json.loads(meta_rows["configuration"])
    assert configuration["starting_cash"] == 350.0
    assert configuration["loaded_config"]["run_name"] == "sample"


def test_output_suffix_must_be_json_or_csv(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.json or \.csv"):
        write_evaluation_report(tmp_path / "bench.txt", _sample_report())


def test_final_test_uses_configured_range_and_records_split(tmp_path: Path) -> None:
    # Synthetic test range; leave the real 700000..700999 range untouched.
    env = SimpleFiggieEnv(EnvConfig(max_steps=2))
    path = tmp_path / "test_policy"
    PPO("MlpPolicy", env, n_steps=8, batch_size=8, verbose=0).save(path)
    env.close()
    config_path = tmp_path / "test.yaml"
    config_path.write_text(yaml.safe_dump({
        "env": {"max_steps": 2},
        "train": {"validation_seed": 9001, "n_eval_episodes": 2},
        "evaluation": {"test_seed": 98000000, "test_episodes": 2},
    }))
    report = run_evaluation(
        model_path=str(path), config_path=str(config_path),
        episodes=None, seed=None, benchmark=False, test=True,
    )
    assert report["seeds"] == [98000000, 98000001]
    assert report["configuration"]["evaluation_split"] == "test"
    for episodes, seed in [(2, None), (None, 9001)]:
        with pytest.raises(ValueError, match="omit --seed and --episodes"):
            run_evaluation(
                model_path="missing.zip", config_path=str(config_path),
                episodes=episodes, seed=seed, benchmark=False, test=True,
            )


def test_main_rejects_unknown_output_before_loading_a_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "figgie-eval",
            "--model-path",
            str(tmp_path / "missing.zip"),
            "--output",
            str(tmp_path / "bench.txt"),
        ],
    )
    with pytest.raises(ValueError, match=r"\.json or \.csv"):
        main()


def test_run_evaluation_writes_seeds_policies_and_paired_differences(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = SimpleFiggieEnv(
        config=EnvConfig(max_steps=2, drift_std=0.0, external_order_flow_prob=0.0, seed=1)
    )
    model = PPO("MlpPolicy", env, n_steps=8, batch_size=8, verbose=0, seed=1)
    model_path = tmp_path / "policy"
    model.save(model_path)
    env.close()

    config_path = tmp_path / "eval.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "run_name": "output_test",
                "seed": 1,
                "env": {
                    "max_steps": 2,
                    "drift_std": 0.0,
                    "external_order_flow_prob": 0.0,
                    "external_fill_prob": 0.0,
                    "starting_cash": 350.0,
                    "opponent_difficulties": ["weak", "average", "bayesian"],
                },
            }
        ),
        encoding="utf-8",
    )

    report = run_evaluation(
        model_path=str(model_path),
        config_path=str(config_path),
        episodes=2,
        seed=11,
        benchmark=True,
    )
    print_report(report)
    printed = capsys.readouterr().out
    assert "Paired profit differences by episode seed:" in printed
    assert "PPO minus" in printed
    assert "Market maker" in printed

    assert report["seeds"] == [11, 12]
    assert report["agent_rng_seeds"] == [500011, 500012]
    assert report["policies"] == [
        "PPO",
        "Hold",
        "Random",
        "Market maker",
        "Value trader",
        "Bayesian",
        "Hunter",
        "Banker",
        "Detective",
        "Bluffer",
    ]
    assert report["base_seed"] == 11
    assert report["configuration"]["starting_cash"] == 350.0
    assert report["configuration"]["loaded_config"]["run_name"] == "output_test"
    assert report["configuration"]["env"]["opponent_difficulties"] == [
        "weak",
        "average",
        "bayesian",
    ]
    assert {row["policy"] for row in report["per_episode"]} == set(report["policies"])
    assert len(report["per_episode"]) == 20
    paired = report["paired_profit_differences"]
    assert [row["other"] for row in paired] == [
        "Hold",
        "Random",
        "Market maker",
        "Value trader",
        "Bayesian",
        "Hunter",
        "Banker",
        "Detective",
        "Bluffer",
    ]
    assert all(row["reference"] == "PPO" and row["episodes"] == 2 for row in paired)

    json_path = tmp_path / "results.json"
    write_evaluation_report(json_path, report)
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["paired_profit_differences"] == report["paired_profit_differences"]

    csv_files = write_evaluation_report(tmp_path / "results.csv", report)
    paired_rows = _read_csv(csv_files[2])
    assert [row["other"] for row in paired_rows] == [row["other"] for row in paired]
    assert float(paired_rows[0]["mean_difference"]) == pytest.approx(paired[0]["mean_difference"])
