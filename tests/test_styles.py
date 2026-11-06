import numpy as np
import pytest

from figgie_rl.agents.baselines import PLAYING_STYLES, OpponentView, policy_for_difficulty
from figgie_rl.agents.styles import Bluffer, SpreadBanker, TapeDetective, hand_posterior
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv


def _view(**overrides) -> OpponentView:
    hand = np.array([1, 2, 4, 3])
    fields = dict(
        inventory=hand.copy(),
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
        initial_inventory=hand.copy(),
        cumulative_signed_flow=np.zeros(4),
    )
    fields.update(overrides)
    return OpponentView(**fields)


@pytest.mark.parametrize("style", PLAYING_STYLES)
def test_style_plays_full_episode_as_opponent(style: str) -> None:
    others = tuple(s for s in PLAYING_STYLES if s != style)
    env = SimpleFiggieEnv(EnvConfig(max_steps=40, opponent_difficulties=others, seed=3))
    env.reset(seed=3)
    done = False
    while not done:
        _, _, terminated, truncated, info = env.step(0)
        done = terminated or truncated
    assert np.all(env.inventories >= 0)
    assert np.all(env.cash >= 0)
    assert info["opponent_difficulties"] == list(others)


def test_env_tracks_cumulative_flow_for_opponent_views() -> None:
    env = SimpleFiggieEnv(EnvConfig(max_steps=30, seed=5))
    env.reset(seed=5)
    for _ in range(30):
        env.step(0)
    view = env._opponent_view(env.opponent_seats[0])
    assert view.cumulative_signed_flow is not None
    assert np.array_equal(view.cumulative_signed_flow, env.cumulative_signed_flow)
    assert np.abs(env.cumulative_signed_flow).sum() >= np.abs(env.belief_flow).sum()


def test_detective_belief_follows_others_buying() -> None:
    detective = TapeDetective()
    quiet = detective.belief(_view())
    flow = np.array([6.0, 0.0, 0.0, 0.0])
    loud = detective.belief(_view(cumulative_signed_flow=flow))
    assert loud[0] > quiet[0]
    np.testing.assert_allclose(quiet, hand_posterior(_view()), rtol=1e-6)


def test_detective_ignores_its_own_buying() -> None:
    detective = TapeDetective()
    hand = np.array([1, 2, 4, 3])
    own_buys = hand + np.array([6, 0, 0, 0])
    view = _view(
        inventory=own_buys,
        initial_inventory=hand,
        cumulative_signed_flow=np.array([6.0, 0.0, 0.0, 0.0]),
    )
    np.testing.assert_allclose(detective.belief(view), hand_posterior(view), rtol=1e-6)


def test_detective_waits_before_buying() -> None:
    detective = TapeDetective()
    rng = np.random.default_rng(0)
    kinds = {detective.act(_view(step=5), rng).kind for _ in range(50)}
    assert "buy" not in kinds


def test_bluffer_buys_decoy_early_and_never_lifts_target_midround() -> None:
    bluffer = Bluffer()
    view = _view()
    posterior = hand_posterior(view)
    target = int(np.argmax(posterior))
    decoy = Bluffer.decoy_suit(posterior, target)
    assert decoy != target

    rng = np.random.default_rng(1)
    early = [bluffer.act(_view(step=2), rng) for _ in range(50)]
    assert any(a.kind == "buy" and a.suit == decoy for a in early)
    assert not any(a.kind == "buy" and a.suit == target for a in early)

    mid = [bluffer.act(_view(step=70, time_remaining=0.4), rng) for _ in range(50)]
    assert not any(a.kind == "buy" for a in mid)


def test_banker_quotes_both_sides_when_nothing_is_mispriced() -> None:
    banker = SpreadBanker()
    rng = np.random.default_rng(2)
    bids = np.full(4, 2.0)
    actions = [banker.act(_view(step=step, best_bid=bids), rng) for step in range(16)]
    assert all(a.kind in {"quote_bid", "quote_ask", "hold"} for a in actions)
    assert {a.kind for a in actions} >= {"quote_bid", "quote_ask"}


def test_banker_sells_cards_it_values_far_below_the_bid() -> None:
    view = _view()
    fair = hand_posterior(view) * 10.0
    action = SpreadBanker().act(view, np.random.default_rng(0))
    assert action.kind == "sell" and fair[action.suit] < 4.0 - 2.0


def test_banker_takes_a_gift() -> None:
    view = _view(best_ask=np.array([6.0, 6.0, 0.5, 6.0]))
    assert hand_posterior(view)[2] * 10 > 2.5
    action = SpreadBanker().act(view, np.random.default_rng(0))
    assert action.kind == "buy" and action.suit == 2


@pytest.mark.parametrize("style", PLAYING_STYLES)
def test_styles_resolve_from_labels(style: str) -> None:
    assert hasattr(policy_for_difficulty(style), "act")
