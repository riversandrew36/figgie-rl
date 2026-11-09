"""The goal-suit teaching input is opt-in and reports the true goal."""

import numpy as np

from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv


def test_goal_oracle_is_absent_by_default_and_correct_when_enabled():
    plain = SimpleFiggieEnv(EnvConfig(market_mode="endogenous"))
    shown = SimpleFiggieEnv(
        EnvConfig(market_mode="endogenous", include_goal_oracle_features=True)
    )
    assert shown.observation_space.shape[0] == plain.observation_space.shape[0] + 4
    assert "goal_oracle" not in plain.observation_spec
    for seed in range(20):
        obs, info = shown.reset(seed=seed)
        expected = np.eye(4)[info["goal_suit_idx"]]
        assert np.array_equal(obs[-4:], expected)
