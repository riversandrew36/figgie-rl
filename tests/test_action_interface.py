"""Action feasibility, privacy, semantic equivalence, and policy persistence."""

from pathlib import Path
import numpy as np
import pytest
import torch
from sb3_contrib import MaskablePPO
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.envs.action_interface import ActionInterface, legal_action_mask
from figgie_rl.agents.structured_policy import (
    StructuredActionHead,
    StructuredMaskablePolicy,
)
from figgie_rl.agents.baselines import OpponentAction


def env():
    return SimpleFiggieEnv(
        EnvConfig(
            market_mode="endogenous",
            max_steps=8,
            include_belief_features=True,
            include_goal_belief_features=True,
            opponent_difficulties=("hunter", "banker", "detective"),
        )
    )


def test_empty_book_and_resources_always_leave_hold():
    e = env()
    e.reset(seed=211)
    i = e.agent_idx
    e.cash[i] = 0
    e.inventories[i] = 0
    mask = legal_action_mask(e)
    assert mask.dtype == bool and mask.shape == (105,)
    assert np.flatnonzero(mask).tolist() == [0]
    e.cash[i] = 10
    e.inventories[i, 0] = 1
    for action in range(105):
        semantic = e.decode_discrete_action(action, 4, "endogenous")
        if semantic.kind in ("buy", "sell"):
            assert not legal_action_mask(e)[action]
    bid = e.encode_semantic_action(OpponentAction("quote_bid", suit=0, limit_price=12))
    ask = e.encode_semantic_action(OpponentAction("quote_ask", suit=0, limit_price=60))
    assert not legal_action_mask(e)[bid]
    assert legal_action_mask(e)[ask]  # expensive quotes remain available


def test_masks_ignore_hidden_state_and_exclude_self_quotes():
    e = env()
    e.reset(seed=211)
    i = e.agent_idx
    j = e.opponent_seats[0]
    e.cash[i] = 10
    e.inventories[i, 0] = 1
    e.ask_quotes[i, 0] = 4
    e.bid_quotes[i, 0] = 6
    buy = e.encode_semantic_action(OpponentAction("buy", suit=0))
    sell = e.encode_semantic_action(OpponentAction("sell", suit=0))
    assert not legal_action_mask(e)[buy] and not legal_action_mask(e)[sell]
    e.ask_quotes[j, 0] = 10
    e.bid_quotes[j, 0] = 8
    before = legal_action_mask(e)
    assert before[buy] and before[sell]
    for other in e.opponent_seats:
        e.cash[other] = 0
        e.inventories[other] = 0
    e.goal_suit_idx = (e.goal_suit_idx + 1) % 4
    np.testing.assert_array_equal(before, legal_action_mask(e))


def test_mask_queries_and_wrapper_preserve_game_transitions():
    plain = env()
    wrapped = ActionInterface(env())
    a, _ = plain.reset(seed=213)
    b, _ = wrapped.reset(seed=213)
    np.testing.assert_array_equal(a, b)
    for index in [1, 17, 35, 50, 70, 90, 104, 0]:
        wrapped.action_masks()
        wrapped.action_masks()
        a, ra, ta, _, ia = plain.step(index)
        b, rb, tb, _, ib = wrapped.step(index)
        np.testing.assert_array_equal(a, b)
        assert ra == rb and ta == tb
        np.testing.assert_array_equal(plain.cash, wrapped.unwrapped.cash)
        np.testing.assert_array_equal(plain.inventories, wrapped.unwrapped.inventories)
    assert ia["final_bankroll"] == ib["final_bankroll"]


def test_factorized_distribution_is_normalized_and_maps_all_actions():
    head = StructuredActionHead(64)
    logits = head(torch.zeros(2, 64))
    probabilities = logits.exp()
    torch.testing.assert_close(probabilities.sum(-1), torch.ones(2))
    torch.testing.assert_close(probabilities, torch.full((2, 105), 1 / 105))
    e = env()
    for index in range(105):
        action = e.decode_discrete_action(index, 4, "endogenous")
        assert e.encode_semantic_action(action) == index
    loss = -logits[0, 1] - logits[1, 44]
    loss.backward()
    assert all(
        layer.weight.grad is not None for layer in (head.kind, head.suit, head.price)
    )


@pytest.mark.parametrize("structured", [False, True])
def test_masked_training_and_checkpoint_roundtrip(tmp_path: Path, structured):
    torch.set_num_threads(1)
    e = ActionInterface(env())
    obs, _ = e.reset(seed=217)
    policy = StructuredMaskablePolicy if structured else "MlpPolicy"
    model = MaskablePPO(
        policy, e, n_steps=8, batch_size=8, gamma=1, seed=217, verbose=0
    )
    model.learn(32)
    obs, _ = e.reset(seed=217)
    mask = e.action_masks()
    expected, _ = model.predict(obs, deterministic=True, action_masks=mask)
    assert mask[int(expected)]
    model.save(tmp_path / "policy")
    restored = MaskablePPO.load(tmp_path / "policy")
    actual, _ = restored.predict(obs, deterministic=True, action_masks=mask)
    assert int(actual) == int(expected)
    e.unwrapped.cash[e.unwrapped.agent_idx] = 0
    e.unwrapped.inventories[e.unwrapped.agent_idx] = 0
    mask = e.action_masks()
    for _ in range(10):
        action, _ = restored.predict(obs, action_masks=mask)
        assert int(action) == 0


def test_cash_check_uses_full_precision_public_price():
    e = SimpleFiggieEnv(EnvConfig(market_mode="exogenous"))
    e.reset(seed=213)
    e.ask_quotes[:] = np.inf
    e.external_ask[0] = 6.0000001
    e.cash[e.agent_idx] = 6.0
    buy = e.encode_semantic_action(OpponentAction("buy", suit=0))
    assert not legal_action_mask(e)[buy]


def reference_mask(env):
    view = env._opponent_view(env.agent_idx)
    _, _, _, _, _, public_ask = env._book_arrays(env.agent_idx)
    result = np.ones(env.action_space.n, dtype=bool)
    for index in range(1, env.action_space.n):
        action = env.decode_discrete_action(
            index, env.num_suits, env.config.market_mode
        )
        suit = int(action.suit)
        if action.kind == "quote_bid":
            result[index] = view.cash >= env._resolve_quote_price(action)
        elif action.kind == "quote_ask":
            result[index] = view.inventory[suit] > 0
        elif action.kind == "buy":
            result[index] = view.ask_available[suit] and view.cash >= public_ask[suit]
        elif action.kind == "sell":
            result[index] = view.bid_available[suit] and view.inventory[suit] > 0
    return result


@pytest.mark.parametrize("market_mode", ["exogenous", "endogenous"])
def test_cached_mask_is_bitwise_equal_to_reference_across_seeded_states(market_mode):
    e = SimpleFiggieEnv(
        EnvConfig(
            market_mode=market_mode,
            max_steps=12,
            include_belief_features=True,
            include_goal_belief_features=True,
            opponent_difficulties=("hunter", "banker", "detective"),
        )
    )
    for seed in range(6):
        e.reset(seed=1100 + seed)
        for _ in range(8):
            np.testing.assert_array_equal(legal_action_mask(e), reference_mask(e))
            e.step(int(e.action_space.sample()))
    e.close()


def test_mask_checks_actual_top_endogenous_quote_rung():
    e = env()
    e.reset(seed=223)
    player = e.agent_idx
    e.cash[player] = 59
    action = e.encode_semantic_action(
        OpponentAction("quote_bid", suit=0, limit_price=60)
    )
    assert not legal_action_mask(e)[action]
    e.cash[player] = 60
    assert legal_action_mask(e)[action]
    e.close()
