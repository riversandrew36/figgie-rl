"""Validate the public data even when the private study archive is unavailable."""

import json
import math
import re
from statistics import mean

import pytest

from scripts.export_rl_showcase import ARENA, RESULTS, START, build_showcase


def test_showcase_matches_archived_study() -> None:
    if not (RESULTS / "step_1_goal_shown/summary.json").exists():
        pytest.skip("Local strong-ladder archive is unavailable")
    assert json.loads((ARENA / "rl_results.json").read_text()) == build_showcase()


def test_showcase_schema_and_inline_copy() -> None:
    path = ARENA / "rl_results.json"
    assert path.stat().st_size < 20_000
    data = json.loads(path.read_text())
    assert data.keys() == {
        "study", "config_sha256", "study_code_revision", "evaluation_seeds", "baselines", "steps",
    }
    assert data["study"] == "strong_ladder_20261115"
    assert re.fullmatch(r"[0-9a-f]{64}", data["config_sha256"])
    assert re.fullmatch(r"[0-9a-f]{40}", data["study_code_revision"])
    assert data["evaluation_seeds"] == [5400000, 5400199]
    assert data["baselines"].keys() == {"Hold", "Bayesian", "Hunter", "Bluffer"}
    assert all(math.isfinite(value) for value in data["baselines"].values())
    assert [step["number"] for step in data["steps"]] == [1, 2, 3]
    for step in data["steps"]:
        assert step.keys() == {"number", "name", "series", "final", "mean"}
        assert [line["seed"] for line in step["series"]] == [901, 902, 903]
        assert step["final"] == [line["points"][-1][1] for line in step["series"]]
        assert step["mean"] == mean(step["final"])
        for line in step["series"]:
            assert line.keys() == {"seed", "points"}
            assert [tick for tick, _ in line["points"]] == list(range(0, 204801, 40960))
            assert all(math.isfinite(profit) for _, profit in line["points"])
    embedded = (ARENA / "figgie_play.html").read_text().split(START, 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == data
