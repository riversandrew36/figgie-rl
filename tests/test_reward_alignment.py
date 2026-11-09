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


def test_expected_value_potential_telescopes_to_profit_and_credits_good_trades():
    import numpy as np
    from figgie_rl.agents.baselines import OpponentAction
    from figgie_rl.envs.mechanics import goal_suit_posterior
    from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv

    config = EnvConfig(
        market_mode="endogenous",
        reward_mode="ev_potential",
        gamma=1.0,
        opponent_difficulties=("hunter", "banker", "detective"),
    )
    env = SimpleFiggieEnv(config)
    env.reset(seed=11)
    start = env._expected_settlement_wealth(env.agent_idx)
    total, done = 0.0, False
    while not done:
        _, reward, terminated, truncated, info = env.step(0)
        total += reward
        done = terminated or truncated
    assert abs(total - (info["final_bankroll"] - 350.0 - start)) < 1e-6

    env.reset(seed=11)
    seat = env.agent_idx
    seller = env.opponent_seats[0]
    posterior = goal_suit_posterior(env.initial_inventories[seat])
    likely = int(np.argmax(posterior))
    assert posterior[likely] > 0.25
    env.inventories[seller, likely] = max(1, env.inventories[seller, likely])
    env.inventories[seat, likely] = 0
    before = env._expected_settlement_wealth(seat)
    env._apply_semantic_action(seller, OpponentAction("quote_ask", suit=likely, limit_price=1))
    env._apply_semantic_action(seat, OpponentAction("buy", suit=likely))
    assert env._expected_settlement_wealth(seat) > before
