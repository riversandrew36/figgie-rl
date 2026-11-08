"""Reward modes reconcile against terminal cash and shaping identities."""
import pytest

from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv


@pytest.mark.parametrize("reward_mode,gamma", [
    ("wealth_delta", .99), ("wealth_delta", 1.0),
    ("terminal_profit", 1.0), ("potential_shaped", .99),
])
def test_reward_identity_matches_settlement(reward_mode, gamma) -> None:
    env = SimpleFiggieEnv(EnvConfig(market_mode="endogenous", max_steps=12,
        reward_mode=reward_mode, gamma=gamma,
        opponent_difficulties=("hunter", "banker", "detective")))
    env.reset(seed=831)
    rewards = []
    for _ in range(12):
        _, reward, terminated, _, info = env.step(0)
        rewards.append(reward)
    final_profit = info["final_bankroll"] - env.config.starting_cash
    if reward_mode == "wealth_delta":
        assert sum(rewards) == pytest.approx(final_profit + env.config.ante)
    else:
        discounted = sum(gamma**i * r for i, r in enumerate(rewards))
        expected = final_profit if gamma == 1 else gamma**11 * final_profit
        assert discounted == pytest.approx(expected, abs=1e-5)
    assert terminated
    env.close()
