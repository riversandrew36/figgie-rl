"""Pilot demonstrations contain only player observations and legal actions."""
import importlib.util
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_imitation_pilot.py"
spec = importlib.util.spec_from_file_location("imitation_pilot", SCRIPT)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_teacher_demonstrations_are_observations_and_discrete_actions() -> None:
    observations, actions = pilot.collect("bayesian", train=True)
    assert observations.shape == (3000, 47)
    assert observations.dtype == np.float32
    assert actions.shape == (3000,)
    assert np.issubdtype(actions.dtype, np.integer)
    assert np.all((0 <= actions) & (actions < 105))
    assert observations.shape[1] == 47  # no hidden-goal label is appended
