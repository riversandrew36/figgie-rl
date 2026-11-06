import numpy as np

from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv


def test_env_reset_and_step_api() -> None:
    env = SimpleFiggieEnv(config=EnvConfig(max_steps=8, seed=123))
    obs, info = env.reset(seed=123)

    assert isinstance(obs, np.ndarray)
    assert obs.shape == env.observation_space.shape
    assert "goal_suit_idx" in info
    assert "observation_spec" in info
    assert len(info["action_meanings"]) == env.action_space.n

    action = env.action_space.sample()
    next_obs, reward, terminated, truncated, step_info = env.step(action)

    assert next_obs.shape == env.observation_space.shape
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert isinstance(step_info, dict)
    assert "reward_breakdown" in step_info


def test_seeded_resets_are_reproducible() -> None:
    cfg = EnvConfig(max_steps=10, seed=42)
    env_a = SimpleFiggieEnv(config=cfg)
    env_b = SimpleFiggieEnv(config=cfg)

    obs_a, info_a = env_a.reset(seed=777)
    obs_b, info_b = env_b.reset(seed=777)

    np.testing.assert_allclose(obs_a, obs_b, atol=1e-8)
    np.testing.assert_array_equal(info_a["suit_distribution"], info_b["suit_distribution"])
    assert info_a["goal_suit_idx"] == info_b["goal_suit_idx"]


def test_step_after_episode_end_raises() -> None:
    env = SimpleFiggieEnv(config=EnvConfig(max_steps=1, seed=5))
    env.reset(seed=5)
    env.step(0)

    try:
        env.step(0)
    except RuntimeError as exc:
        assert "reset" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when stepping after episode end")


def test_reward_breakdown_sums_to_reward() -> None:
    env = SimpleFiggieEnv(config=EnvConfig(max_steps=3, drift_std=0.0, seed=11))
    env.reset(seed=11)
    _, reward, _, _, info = env.step(0)

    breakdown = info["reward_breakdown"]
    total = (
        breakdown["trade_reward"]
        + breakdown["inventory_reward"]
        + breakdown["settlement_reward"]
    )
    assert abs(float(reward) - float(total)) < 1e-8


def test_action_descriptions_cover_space() -> None:
    env = SimpleFiggieEnv(config=EnvConfig(seed=3))
    descriptions = [
        env.describe_action(action_idx, env.num_suits)
        for action_idx in range(env.action_space.n)
    ]

    assert descriptions[0] == "hold"
    assert any(desc.startswith("buy ") for desc in descriptions)
    assert any(desc.startswith("quote_bid ") for desc in descriptions)


def test_external_order_flow_can_fill_agent_quote() -> None:
    env = SimpleFiggieEnv(
        config=EnvConfig(
            max_steps=5,
            drift_std=0.0,
            external_order_flow_prob=1.0,
            seed=123,
        )
    )
    env.reset(seed=123)
    env.agent_bid_quote[:] = env.external_bid + 1.0
    env.agent_ask_quote[:] = env.external_ask - 1.0

    starting_trades = env.agent_trade_count
    for _ in range(10):
        env._simulate_external_order_flow()
        if env.agent_trade_count > starting_trades:
            break

    assert env.agent_trade_count > starting_trades


def test_unseeded_resets_advance_rng_state() -> None:
    env = SimpleFiggieEnv(config=EnvConfig(max_steps=10, seed=42))
    _, info_a = env.reset()
    _, info_b = env.reset()

    assert not np.array_equal(info_a["suit_distribution"], info_b["suit_distribution"])


def test_decode_discrete_action_preserves_quote_level_zero() -> None:
    action = SimpleFiggieEnv.decode_discrete_action(action=1, num_suits=4)
    assert action.kind == "quote_bid"
    assert action.price_level == 0


def test_opponent_difficulties_yaml_list_normalized() -> None:
    cfg = EnvConfig(opponent_difficulties=["weak", "tough", "average"])
    assert cfg.opponent_difficulties == ("weak", "tough", "average")


def test_opponent_difficulties_in_reset_info() -> None:
    env = SimpleFiggieEnv(
        config=EnvConfig(max_steps=4, seed=1, opponent_difficulties=("weak", "weak", "tough"))
    )
    _, info = env.reset(seed=1)
    assert info["opponent_difficulties"] == ["weak", "weak", "tough"]
    assert env.agent_idx not in env.opponent_seats
    assert info["opponent_difficulty_by_player"] == {
        f"player_{seat}": label
        for seat, label in zip(env.opponent_seats, ("weak", "weak", "tough"))
    }
    assert info["opponent_difficulty_score"] == 2.0


def test_invalid_opponent_difficulty_raises() -> None:
    try:
        EnvConfig(opponent_difficulties=("weak", "average", "impossible"))
    except ValueError as exc:
        assert "Invalid opponent_difficulties" in str(exc)
    else:
        raise AssertionError("Expected ValueError for bad difficulty label")


def test_quotes_join_market_and_expire() -> None:
    env = SimpleFiggieEnv(
        config=EnvConfig(max_steps=10, quote_ttl_steps=2, drift_std=0.0, seed=5)
    )
    env.reset(seed=5)
    env._apply_semantic_action(env.agent_idx, env._decode_agent_action(3))

    price, owner = env._best_bid(0)
    assert price > env.external_bid[0]
    assert owner == env.agent_idx

    env._age_and_expire_quotes()
    env._age_and_expire_quotes()
    assert not np.isfinite(env.agent_bid_quote[0])


def test_signed_flow_tracks_aggressor_side() -> None:
    env = SimpleFiggieEnv(config=EnvConfig(seed=9))
    env.reset(seed=9)
    env._trade(0, -1, 0, 5.0, by_quote_fill=False, aggressor_side="buy")
    assert env.last_trade_signed_volume[0] == 1.0
    env._trade(-1, 0, 0, 5.0, by_quote_fill=False, aggressor_side="sell")
    assert env.last_trade_signed_volume[0] == -1.0


def test_natural_horizon_terminates_and_replaces_inventory_mark() -> None:
    env = SimpleFiggieEnv(
        config=EnvConfig(
            max_steps=1,
            drift_std=0.0,
            external_order_flow_prob=0.0,
            seed=12,
        )
    )
    env.reset(seed=12)
    initial_mark = env._mark_to_market(env.agent_idx)
    _, reward, terminated, truncated, info = env.step(0)

    assert terminated is True
    assert truncated is False
    assert np.isclose(reward, info["final_bankroll"] - initial_mark)
    assert np.sum(env.inventories) == 0
    assert len(info["final_bankrolls"]) == env.config.num_players
    assert 1 <= info["final_rank"] <= env.config.num_players


def test_trading_conserves_cards_and_cash_before_settlement() -> None:
    env = SimpleFiggieEnv(
        config=EnvConfig(max_steps=20, external_order_flow_prob=1.0, seed=14)
    )
    env.reset(seed=14)
    expected_cash = env.config.num_players * (env.config.starting_cash - env.config.ante)

    for _ in range(env.config.max_steps - 1):
        env.step(env.action_space.sample())
        assert int(np.sum(env.inventories)) == 40
        assert np.isclose(np.sum(env.cash), expected_cash)
