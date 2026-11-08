"""Protect held-out splits, checkpoint selection, and paired report reuse."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts/run_rl_study.py"
spec = importlib.util.spec_from_file_location("rl_study", MODULE)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def test_comparison_budgets_match_and_splits_are_disjoint() -> None:
    study.check_design(study.SPEC)
    cfg = study.config_for("fixed", 17, study.SPEC)
    assert cfg["train"]["total_timesteps"] == 122880
    assert cfg["evaluation"]["test_seed"] == 1400000
    invalid = deepcopy(study.SPEC)
    invalid["final"] = invalid["validation"]
    with pytest.raises(AssertionError):
        study.check_design(invalid)
    invalid = deepcopy(study.SPEC)
    invalid["self_play_chunk_timesteps"] += 1024
    with pytest.raises(AssertionError):
        study.check_design(invalid)


def test_selection_uses_validation_metrics_and_retains_earliest_exact_tie() -> None:
    def candidate(name, bankroll, wins, rank, test_profit):
        return {"model": name, "selection": {"mean_final_bankroll": bankroll,
                "win_rate": wins, "mean_rank": rank}, "irrelevant_test_profit": test_profit}
    entries = [candidate("early", 360, 0.3, 2, -100),
               candidate("late_tie", 360, 0.3, 2, 999),
               candidate("less_cash", 359, 1, 1, 999)]
    assert study.choose_checkpoint(entries)["model"] == "early"
    entries.append(candidate("higher_cash", 361, 0, 4, -999))
    assert study.choose_checkpoint(entries)["model"] == "higher_cash"


def test_baseline_cache_recomputes_paired_differences_for_new_model() -> None:
    def report(profits, benchmark):
        policies = ["PPO", "Hold"] if benchmark else ["PPO"]
        rows = [{"policy": "PPO", "profit": p} for p in profits]
        if benchmark:
            rows += [{"policy": "Hold", "profit": p} for p in [2, 4, 6]]
        return {"seeds": [90, 91, 92], "policies": policies, "per_episode": rows,
                "configuration": {"env": {"market_mode": "endogenous"}},
                "aggregates": [{"policy": p} for p in policies], "benchmark": benchmark}
    original = report([100, 100, 100], True)
    candidate = report([3, 5, 7], False)
    merged = study.merge_baselines(candidate, original, "baseline.json")
    assert merged["paired_profit_differences"][0]["mean_difference"] == 1
    assert merged["paired_profit_differences"][0]["ci95"] == 0
    assert not candidate["benchmark"]
    invalid = deepcopy(candidate)
    invalid["configuration"]["env"]["market_mode"] = "exogenous"
    with pytest.raises(AssertionError):
        study.merge_baselines(invalid, original, "bad.json")


def test_frozen_manifest_rejects_changed_checkpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(study, "OUTPUT", tmp_path)
    monkeypatch.setattr(study, "source_hashes", lambda: {"source": "hash"})
    model = tmp_path / "model.zip"
    model.write_bytes(b"original")
    study.save(tmp_path / "frozen_selection.json", {
        "source_hashes": {"source": "hash"},
        "models": {"selected": {"model": str(model), "model_sha256": study.sha(model)}},
    })
    study.verify_frozen()
    model.write_bytes(b"changed")
    with pytest.raises(AssertionError, match="Checkpoint changed"):
        study.verify_frozen()
