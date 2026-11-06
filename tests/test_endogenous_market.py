"""Endogenous market: player quotes only, no forced fills, official pot."""

import numpy as np

from figgie_rl.agents.baselines import NaiveGoalBuyer, OpponentAction, OpponentView
from figgie_rl.envs.simple_figgie_env import (
    ENDOGENOUS_PRICE_LADDER,
    EnvConfig,
    SimpleFiggieEnv,
)


class _Hold:
    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        del view, rng
        return OpponentAction("hold")


def _endogenous(**overrides: object) -> SimpleFiggieEnv:
    config = EnvConfig(
        market_mode="endogenous",
        max_steps=8,
        external_fill_prob=1.0,
        external_order_flow_prob=1.0,
        seed=1,
        **overrides,
    )
    return SimpleFiggieEnv(config=config, opponent_policies=[_Hold(), _Hold(), _Hold()])


def test_default_market_mode_keeps_the_exogenous_action_space() -> None:
    env = SimpleFiggieEnv(config=EnvConfig(seed=1))
    assert env.config.market_mode == "exogenous"
    assert env.action_space.n == 33
    _, info = env.reset(seed=1)
    assert info["market_mode"] == "exogenous"
    assert "bid_available" not in info["observation_spec"]


def test_invalid_market_mode_raises() -> None:
    try:
        EnvConfig(market_mode="hybrid")
    except ValueError as exc:
        assert "market_mode" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_endogenous_action_ladder_is_absolute() -> None:
    env = _endogenous()
    assert env.action_space.n == 1 + 4 * (2 * len(ENDOGENOUS_PRICE_LADDER) + 2)
    decoded = env.decode_discrete_action(1, env.num_suits, market_mode="endogenous")
    assert decoded.kind == "quote_bid"
    assert decoded.limit_price == ENDOGENOUS_PRICE_LADDER[0]
    assert "price=1" in env.describe_action(1, env.num_suits, market_mode="endogenous")
    _, info = env.reset(seed=1)
    assert info["observation_spec"]["bid_available"] == 4
    assert info["observation_spec"]["ask_available"] == 4
    assert env.observation_space.shape == (31 + 8,)


def test_buy_against_an_empty_book_does_not_force_a_trade() -> None:
    env = _endogenous()
    env.reset(seed=1)
    before_cards = env.inventories.copy()
    before_cash = env.cash.copy()
    buy = next(
        index
        for index, (kind, suit, _) in enumerate(env._action_table)
        if kind == "buy" and suit == 0
    )
    env.step(buy)

    np.testing.assert_array_equal(env.inventories, before_cards)
    np.testing.assert_allclose(env.cash, before_cash)


def test_trade_requires_a_resting_player_quote() -> None:
    env = _endogenous()
    env.reset(seed=1)
    env.inventories[:] = 0
    env.inventories[0, 0] = 2
    env.inventories[1, 1] = 2
    env.cash[:] = 100.0

    env._apply_semantic_action(0, OpponentAction("quote_ask", suit=0, limit_price=8))
    env._apply_semantic_action(1, OpponentAction("buy", suit=0))

    assert env.inventories[0, 0] == 1
    assert env.inventories[1, 0] == 1
    assert env.cash[0] == 108.0
    assert env.cash[1] == 92.0
    assert env.has_traded[0]
    assert int(env.inventories.sum()) == 4


def test_legacy_aggressive_bid_is_twenty_dollars() -> None:
    env = _endogenous()
    env.reset(seed=1)
    env._apply_semantic_action(0, OpponentAction("quote_bid", suit=2, price_level=2))
    price, owner = env._best_bid(2)
    assert price == 20.0
    assert owner == 0


def test_quotes_are_stored_by_seat_when_the_learner_is_not_seat_zero() -> None:
    env = SimpleFiggieEnv(config=EnvConfig(max_steps=4, seed=3))
    env.reset(seed=3)
    env.agent_idx = 2
    env._apply_semantic_action(0, OpponentAction("quote_bid", suit=0, price_level=2))
    env._apply_semantic_action(3, OpponentAction("quote_ask", suit=1, price_level=0))

    assert np.isfinite(env.bid_quotes[0, 0])
    assert np.isfinite(env.ask_quotes[3, 1])
    assert not np.isfinite(env.bid_quotes[3, 0])


def test_endogenous_episode_conserves_cards_and_the_pot() -> None:
    env = SimpleFiggieEnv(
        config=EnvConfig(
            market_mode="endogenous",
            max_steps=6,
            external_fill_prob=1.0,
            external_order_flow_prob=1.0,
            pot_conserving_settlement=True,
            seed=4,
            opponent_difficulties=("weak", "average", "tough"),
        )
    )
    env.reset(seed=4)
    for _ in range(env.config.max_steps - 1):
        env.step(env.action_space.sample())
        assert int(env.inventories.sum()) == 40
        assert np.isclose(env.cash.sum(), 4 * (env.config.starting_cash - env.config.ante))

    _, _, terminated, _, info = env.step(0)
    assert terminated
    assert np.isclose(info["final_bankrolls"].sum(), 4 * env.config.starting_cash)


def test_naive_buyer_lifts_a_finite_ask_and_does_not_invent_one() -> None:
    buyer = NaiveGoalBuyer()
    hand = np.array([8, 1, 1, 0], dtype=np.int32)
    rng = np.random.default_rng(0)
    offered = OpponentView(
        inventory=hand.copy(),
        cash=300.0,
        best_bid=np.zeros(4),
        best_ask=np.array([1.0e6, 1.0e6, 4.0, 1.0e6]),
        own_bid_quote=np.full(4, -np.inf),
        own_ask_quote=np.full(4, np.inf),
        last_trade_price=np.zeros(4),
        last_trade_signed_volume=np.zeros(4),
        belief_flow=np.zeros(4),
        time_remaining=1.0,
        step=0,
        max_steps=10,
        initial_inventory=hand.copy(),
    )
    # Eight spades makes clubs the most likely goal (same-color partner of a
    # likely 12-spade suit). The only finite ask is hearts, so the buyer bids
    # its target instead of lifting a different suit.
    action = buyer.act(offered, rng)
    assert action.kind == "quote_bid"
    assert action.suit == 1

    clubs_offered = OpponentView(
        inventory=hand.copy(),
        cash=300.0,
        best_bid=np.zeros(4),
        best_ask=np.array([1.0e6, 9.0, 1.0e6, 1.0e6]),
        own_bid_quote=np.full(4, -np.inf),
        own_ask_quote=np.full(4, np.inf),
        last_trade_price=np.zeros(4),
        last_trade_signed_volume=np.zeros(4),
        belief_flow=np.zeros(4),
        time_remaining=1.0,
        step=0,
        max_steps=10,
        initial_inventory=hand.copy(),
    )
    lifted = buyer.act(clubs_offered, rng)
    assert lifted.kind == "buy"
    assert lifted.suit == 1
