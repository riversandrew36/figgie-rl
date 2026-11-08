"""Official quote rules, the legacy switch, and learner-only reward scaling."""

import numpy as np
import pytest

from figgie_rl.agents.baselines import OpponentAction as A
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv


class Hold:
    def act(self, view, rng):
        return A("hold")


def market(rules="official", mode="endogenous", **config):
    env = SimpleFiggieEnv(
        EnvConfig(market_mode=mode, quote_rules=rules, **config),
        opponent_policies=[Hold(), Hold(), Hold()],
    )
    env.reset(seed=1)
    env.inventories[:] = 2
    return env


def test_unbacked_ask_and_bid_are_rejected():
    env = market()
    env.inventories[1, 0] = 0
    env.cash[2] = 5.0
    env._apply_semantic_action(1, A("quote_ask", suit=0, limit_price=2))
    env._apply_semantic_action(2, A("quote_bid", suit=0, limit_price=20))
    assert env._best_ask(0) == (np.inf, None)
    assert env._best_bid(0) == (-np.inf, None)


@pytest.mark.parametrize(
    "resting, crossing, buyer, seller",
    [
        (A("quote_ask", suit=0, limit_price=8), A("quote_bid", suit=0, limit_price=12), 2, 1),
        (A("quote_bid", suit=0, limit_price=8), A("quote_ask", suit=0, limit_price=4), 1, 2),
    ],
)
def test_crossing_quote_trades_at_resting_price(resting, crossing, buyer, seller):
    env = market()
    env._apply_semantic_action(1, resting)
    # Seat 1 rests; seat 2 crosses, so the mapping below names buyer and seller by seat.
    cash = env.cash.copy()
    env._apply_semantic_action(2, crossing)
    assert env.inventories[buyer, 0] == 3 and env.inventories[seller, 0] == 1
    assert env.cash[buyer] == cash[buyer] - 8 and env.cash[seller] == cash[seller] + 8


def test_a_trade_clears_every_quote_in_every_suit():
    env = market()
    env._apply_semantic_action(1, A("quote_bid", suit=0, limit_price=9))
    env._apply_semantic_action(2, A("quote_ask", suit=3, limit_price=30))
    env._apply_semantic_action(3, A("quote_bid", suit=1, limit_price=4))
    env._apply_semantic_action(0, A("sell", suit=0))
    assert not np.isfinite(env.bid_quotes).any()
    assert not np.isfinite(env.ask_quotes).any()
    assert (env.bid_quote_ages == -1).all() and (env.ask_quote_ages == -1).all()
    held = env.inventories[0, 0]
    env._apply_semantic_action(0, A("sell", suit=0))
    assert env.inventories[0, 0] == held


def test_legacy_rules_keep_original_behavior():
    env = market("legacy")
    env.inventories[1, 0] = 0
    env._apply_semantic_action(1, A("quote_ask", suit=0, limit_price=2))
    assert env.ask_quotes[1, 0] == 2
    env._apply_semantic_action(2, A("quote_bid", suit=0, limit_price=9))
    env._apply_semantic_action(0, A("sell", suit=0))
    env._apply_semantic_action(0, A("sell", suit=0))
    assert env.inventories[0, 0] == 0 and env.bid_quotes[2, 0] == 9


@pytest.mark.parametrize("mode", ["exogenous", "endogenous"])
def test_official_book_stays_backed_and_uncrossed_in_real_play(mode):
    lineup = ("weak", "average", "tough")
    for seed in range(20):
        env = SimpleFiggieEnv(EnvConfig(market_mode=mode, opponent_difficulties=lineup))
        env.reset(seed=seed)
        done = False
        while not done:
            for suit in range(4):
                bids = env.bid_quotes[:, suit]
                asks = env.ask_quotes[:, suit]
                live_bids = np.isfinite(bids)
                live_asks = np.isfinite(asks)
                assert (env.cash[live_bids] >= bids[live_bids]).all()
                assert (env.inventories[live_asks, suit] > 0).all()
                for buyer in np.flatnonzero(live_bids):
                    for seller in np.flatnonzero(live_asks):
                        assert buyer == seller or bids[buyer] < asks[seller]
            _, _, terminated, truncated, info = env.step(0)
            done = terminated or truncated
        assert info["final_bankrolls"].sum() == pytest.approx(1400.0)


def test_reward_scale_changes_only_the_returned_reward():
    def play(scale):
        env = SimpleFiggieEnv(
            EnvConfig(
                market_mode="endogenous",
                reward_scale=scale,
                opponent_difficulties=("hunter", "banker", "detective"),
            )
        )
        env.reset(seed=3)
        rewards, done = [], False
        while not done:
            _, reward, terminated, truncated, info = env.step(0)
            rewards.append(reward)
            done = terminated or truncated
        return np.array(rewards), info

    raw, raw_info = play(1.0)
    scaled, scaled_info = play(0.02)
    assert scaled == pytest.approx(raw * 0.02)
    assert scaled_info["final_bankroll"] == raw_info["final_bankroll"]
    assert scaled_info["reward_breakdown"] == raw_info["reward_breakdown"]


def test_invalid_settings_are_rejected():
    with pytest.raises(ValueError):
        EnvConfig(quote_rules="other")
    with pytest.raises(ValueError):
        EnvConfig(reward_scale=0.0)
