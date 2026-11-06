"""Endogenous style quotes follow belief. Exogenous actions stay on price_level."""

import numpy as np

from figgie_rl.agents.baselines import OpponentView
from figgie_rl.agents.styles import Bluffer, GoalHunter, SpreadBanker, TapeDetective
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv

LEGACY_PRICES = {4.0, 8.0, 10.0, 12.0, 20.0, 30.0}
LOW_HAND = np.array([3, 3, 2, 2])
HIGH_HAND = np.array([1, 6, 2, 1])


def _view(hand: np.ndarray | None = None, **overrides) -> OpponentView:
    cards = np.array([1, 2, 4, 3] if hand is None else hand, dtype=np.int32)
    fields = dict(
        inventory=cards.copy(),
        cash=300.0,
        best_bid=np.full(4, 4.0),
        best_ask=np.full(4, 6.0),
        own_bid_quote=np.full(4, -np.inf),
        own_ask_quote=np.full(4, np.inf),
        last_trade_price=np.full(4, 5.0),
        last_trade_signed_volume=np.zeros(4),
        belief_flow=np.zeros(4),
        time_remaining=1.0,
        step=0,
        max_steps=120,
        initial_inventory=cards.copy(),
        cumulative_signed_flow=np.zeros(4),
        market_mode="exogenous",
    )
    fields.update(overrides)
    return OpponentView(**fields)


def _empty(**overrides) -> OpponentView:
    return _view(
        best_bid=np.zeros(4),
        best_ask=np.full(4, 1.0e6),
        last_trade_price=np.zeros(4),
        market_mode="endogenous",
        **overrides,
    )


def _signature(action) -> tuple:
    return (action.kind, action.suit, action.price_level, action.limit_price)


# Recorded from the exogenous bots before limit_price existed. Seed 0, four draws.
EXOGENOUS_GOLDEN = {
    "wide_ask_s0": {
        "hunter": [("quote_bid", 3, 2, None), ("sell", 1, 1, None), ("sell", 1, 1, None), ("sell", 1, 1, None)],
        "banker": [("sell", 1, 1, None), ("sell", 1, 1, None), ("sell", 1, 1, None), ("sell", 1, 1, None)],
        "detective": [("quote_bid", 3, 0, None), ("hold", None, 1, None), ("hold", None, 1, None), ("hold", None, 1, None)],
        "bluffer": [("quote_bid", 3, 0, None), ("buy", 1, 1, None), ("buy", 1, 1, None), ("buy", 1, 1, None)],
    },
    "bid2_ask8_s0": {
        "hunter": [("buy", 3, 1, None)] * 4,
        "banker": [("quote_bid", 0, 0, None)] * 4,
        "detective": [("quote_bid", 3, 0, None), ("hold", None, 1, None), ("hold", None, 1, None), ("hold", None, 1, None)],
        "bluffer": [("quote_bid", 3, 0, None), ("buy", 1, 1, None), ("buy", 1, 1, None), ("buy", 1, 1, None)],
    },
    "bid2_ask8_s1": {
        "hunter": [("buy", 3, 1, None)] * 4,
        "banker": [("quote_ask", 1, 0, None)] * 4,
        "detective": [("quote_bid", 3, 0, None), ("hold", None, 1, None), ("hold", None, 1, None), ("hold", None, 1, None)],
        "bluffer": [("quote_bid", 3, 0, None), ("buy", 1, 1, None), ("buy", 1, 1, None), ("buy", 1, 1, None)],
    },
    "base_s40": {
        "hunter": [("buy", 3, 1, None)] * 4,
        "banker": [("sell", 1, 1, None)] * 4,
        "detective": [("quote_bid", 3, 0, None), ("hold", None, 1, None), ("hold", None, 1, None), ("hold", None, 1, None)],
        "bluffer": [("quote_bid", 3, 1, None), ("quote_ask", 1, 2, None), ("quote_ask", 1, 2, None), ("quote_ask", 1, 2, None)],
    },
    "base_s100": {
        "hunter": [("buy", 3, 1, None)] * 4,
        "banker": [("sell", 1, 1, None)] * 4,
        "detective": [("quote_bid", 3, 0, None), ("hold", None, 1, None), ("hold", None, 1, None), ("hold", None, 1, None)],
        "bluffer": [("quote_bid", 3, 1, None), ("sell", 1, 1, None), ("sell", 1, 1, None), ("sell", 1, 1, None)],
    },
    "cheap2": {
        "hunter": [("buy", 3, 1, None)] * 4,
        "banker": [("buy", 2, 1, None)] * 4,
        "detective": [("quote_bid", 3, 0, None), ("hold", None, 1, None), ("hold", None, 1, None), ("hold", None, 1, None)],
        "bluffer": [("quote_bid", 3, 0, None), ("buy", 1, 1, None), ("buy", 1, 1, None), ("buy", 1, 1, None)],
    },
}


def _case_view(name: str) -> OpponentView:
    if name == "wide_ask_s0":
        return _view(step=0, best_ask=np.full(4, 30.0))
    if name == "bid2_ask8_s0":
        return _view(step=0, best_bid=np.full(4, 2.0), best_ask=np.full(4, 8.0))
    if name == "bid2_ask8_s1":
        return _view(step=1, best_bid=np.full(4, 2.0), best_ask=np.full(4, 8.0))
    if name == "base_s40":
        return _view(step=40)
    if name == "base_s100":
        return _view(step=100)
    if name == "cheap2":
        return _view(step=10, best_ask=np.array([6.0, 6.0, 0.5, 6.0]))
    raise AssertionError(name)


def test_exogenous_actions_match_the_recorded_price_levels() -> None:
    bots = {
        "hunter": GoalHunter(),
        "banker": SpreadBanker(),
        "detective": TapeDetective(),
        "bluffer": Bluffer(),
    }
    for case, expected in EXOGENOUS_GOLDEN.items():
        view = _case_view(case)
        for name, bot in bots.items():
            rng = np.random.default_rng(0)
            got = [_signature(bot.act(view, rng)) for _ in range(4)]
            assert got == expected[name]
            assert all(action[3] is None for action in got)


def _bid(bot, hand: np.ndarray, **overrides) -> float:
    action = bot.act(_empty(hand=hand, **overrides), np.random.default_rng(0))
    assert action.kind == "quote_bid"
    assert action.limit_price is not None
    return float(action.limit_price)


def test_hunter_banker_and_detective_bid_more_when_the_posterior_is_higher() -> None:
    hunter_low = _bid(GoalHunter(), LOW_HAND)
    hunter_high = _bid(GoalHunter(), HIGH_HAND)
    assert hunter_high > hunter_low

    banker_low = _bid(SpreadBanker(), LOW_HAND)
    banker_high = _bid(SpreadBanker(), HIGH_HAND)
    assert banker_high > banker_low

    detective_low = _bid(TapeDetective(), LOW_HAND)
    detective_high = _bid(TapeDetective(), HIGH_HAND)
    assert detective_high > detective_low


def test_detective_raises_its_price_when_the_tape_buys_a_suit() -> None:
    detective = TapeDetective()
    quiet = _bid(detective, LOW_HAND)
    loud = _bid(
        detective,
        LOW_HAND,
        cumulative_signed_flow=np.array([2.0, 0.0, 0.0, 0.0]),
    )
    assert loud > quiet


def test_banker_quotes_are_two_sided_and_follow_the_posterior() -> None:
    def book(hand: np.ndarray) -> dict[int, dict[str, float]]:
        quotes: dict[int, dict[str, float]] = {}
        banker = SpreadBanker()
        for step in range(8):
            action = banker.act(_empty(hand=hand, step=step), np.random.default_rng(0))
            assert action.kind in {"quote_bid", "quote_ask"}
            assert action.limit_price is not None
            quotes.setdefault(int(action.suit), {})[action.kind] = float(action.limit_price)
        return quotes

    low = book(LOW_HAND)
    high = book(HIGH_HAND)
    assert set(low) == {0, 1, 2, 3}
    for suit, sides in low.items():
        assert sides["quote_bid"] < sides["quote_ask"]
        assert high[suit]["quote_bid"] != sides["quote_bid"] or high[suit]["quote_ask"] != sides["quote_ask"]
    # Suit 0 is the one whose posterior actually jumps between these two hands.
    assert high[0]["quote_bid"] > low[0]["quote_bid"]
    assert high[0]["quote_ask"] > low[0]["quote_ask"]


def test_empty_book_is_not_traded() -> None:
    bots = [GoalHunter(), SpreadBanker(), TapeDetective(), Bluffer()]
    for step in (0, 2, 40, 70, 100, 110):
        view = _empty(step=step, hand=np.array([1, 2, 4, 3]))
        for bot in bots:
            for seed in range(5):
                action = bot.act(view, np.random.default_rng(seed))
                assert action.kind not in {"buy", "sell"}


def test_bids_stay_within_cash_and_asks_need_inventory() -> None:
    hunter = GoalHunter()
    action = hunter.act(_empty(hand=HIGH_HAND, cash=3.0), np.random.default_rng(0))
    assert action.kind == "quote_bid"
    assert action.limit_price is not None
    assert action.limit_price <= 3.0

    banker = SpreadBanker()
    held = np.array([0, 0, 0, 10])
    for step in range(16):
        action = banker.act(_empty(hand=held, step=step), np.random.default_rng(0))
        if action.kind == "quote_ask":
            assert int(held[int(action.suit)]) > 0
        if action.kind == "quote_bid":
            assert action.limit_price is not None
            assert action.limit_price <= 300.0


def test_bluffer_will_not_pay_above_its_decoy_cap() -> None:
    bluffer = Bluffer()
    hand = np.array([1, 2, 4, 3])
    expensive = _view(
        hand=hand,
        market_mode="endogenous",
        step=2,
        best_bid=np.zeros(4),
        best_ask=np.array([1.0e6, bluffer.bluff_max_price + 0.01, 1.0e6, 1.0e6]),
    )
    capped = _view(
        hand=hand,
        market_mode="endogenous",
        step=2,
        best_bid=np.zeros(4),
        best_ask=np.array([1.0e6, bluffer.bluff_max_price, 1.0e6, 1.0e6]),
    )
    expensive_actions = [bluffer.act(expensive, np.random.default_rng(seed)) for seed in range(20)]
    assert not any(action.kind == "buy" for action in expensive_actions)
    capped_actions = [bluffer.act(capped, np.random.default_rng(seed)) for seed in range(20)]
    assert any(action.kind == "buy" and action.suit == 1 for action in capped_actions)


def test_endogenous_episodes_quote_off_the_legacy_shim_and_conserve_the_pot() -> None:
    env = SimpleFiggieEnv(
        config=EnvConfig(
            market_mode="endogenous",
            max_steps=40,
            pot_conserving_settlement=True,
            opponent_difficulties=("hunter", "banker", "bluffer"),
            external_fill_prob=1.0,
            external_order_flow_prob=1.0,
        )
    )
    off_shim = False
    for episode in range(20):
        env.reset(seed=episode)
        done = False
        info = {}
        while not done:
            _, _, terminated, truncated, info = env.step(0)
            done = terminated or truncated
            if not done:
                assert int(env.inventories.sum()) == 40
                ante_cash = env.config.num_players * (env.config.starting_cash - env.config.ante)
                assert np.isclose(env.cash.sum(), ante_cash)
            finite = np.concatenate([env.bid_quotes[np.isfinite(env.bid_quotes)], env.ask_quotes[np.isfinite(env.ask_quotes)]])
            if any(float(price) not in LEGACY_PRICES for price in finite):
                off_shim = True
        assert np.isclose(info["final_bankrolls"].sum(), env.config.num_players * env.config.starting_cash)
    assert off_shim
    env.close()
