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


def test_hidden_blocks_keep_width_and_report_zeros():
    import pytest

    shown = SimpleFiggieEnv(EnvConfig(
        market_mode="endogenous", include_goal_oracle_features=True,
        include_goal_belief_features=True,
    ))
    hidden = SimpleFiggieEnv(EnvConfig(
        market_mode="endogenous", include_goal_oracle_features=True,
        include_goal_belief_features=True,
        hidden_observation_blocks=("goal_oracle", "goal_suit_posterior"),
    ))
    assert hidden.observation_space.shape == shown.observation_space.shape
    assert shown.goal_shown_to_learner and not hidden.goal_shown_to_learner
    full, _ = shown.reset(seed=3)
    blanked, _ = hidden.reset(seed=3)
    start, slices = 0, {}
    for name, width in shown.observation_spec.items():
        slices[name] = slice(start, start + width)
        start += width
    for name, part in slices.items():
        if name in ("goal_oracle", "goal_suit_posterior"):
            assert not blanked[part].any() and full[part].any()
        else:
            assert np.array_equal(blanked[part], full[part])
    with pytest.raises(ValueError):
        SimpleFiggieEnv(EnvConfig(
            market_mode="endogenous", hidden_observation_blocks=("goal_oracle",),
        ))


def test_hidden_goal_falls_back_to_hand_posterior_in_reward():
    def potential(hide):
        env = SimpleFiggieEnv(EnvConfig(
            market_mode="endogenous", reward_mode="ev_potential", gamma=1.0,
            include_goal_oracle_features=True, hidden_observation_blocks=hide,
        ))
        env.reset(seed=11)
        return env._expected_settlement_wealth(env.agent_idx)

    plain = SimpleFiggieEnv(EnvConfig(market_mode="endogenous", reward_mode="ev_potential"))
    plain.reset(seed=11)
    assert np.isclose(potential(("goal_oracle",)), plain._expected_settlement_wealth(plain.agent_idx))
    assert not np.isclose(potential(()), potential(("goal_oracle",)))
