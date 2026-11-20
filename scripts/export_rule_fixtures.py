"""Export deterministic official-rule scenarios shared with the browser tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from figgie_rl.agents.baselines import OpponentAction
from figgie_rl.envs.mechanics import settle_round
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests" / "browser" / "fixtures" / "official_rules.json"


class Hold:
    """No-op opponents; fixtures apply each named action directly."""

    def act(self, view, rng):  # noqa: ANN001, ARG002
        return OpponentAction("hold")


DEAL_8 = [
    [3, 3, 2, 2],
    [3, 3, 2, 2],
    [1, 3, 4, 2],
    [1, 3, 2, 4],
]
DEAL_10 = [
    [4, 3, 2, 1],
    [4, 3, 1, 2],
    [1, 3, 4, 2],
    [1, 3, 3, 3],
]
DEAL_UNBACKED_ASK = [
    [3, 3, 2, 2],
    [0, 4, 3, 3],
    [3, 2, 3, 2],
    [2, 3, 2, 3],
]


def _action(player: int, kind: str, suit: int, price: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"player": player, "action": {"kind": kind, "suit": suit}}
    if price is not None:
        result["action"]["price"] = price
    return result


SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "unbacked_bid",
        "inventories": DEAL_8,
        "goalSuitIdx": 0,
        "startingCash": 60,
        "steps": [_action(0, "quote_bid", 0, 11)],
    },
    {
        "name": "unbacked_ask",
        "inventories": DEAL_UNBACKED_ASK,
        "goalSuitIdx": 0,
        "steps": [_action(1, "quote_ask", 0, 8)],
    },
    {
        "name": "resting_ask_lifted_by_crossing_bid",
        "inventories": DEAL_8,
        "goalSuitIdx": 0,
        "steps": [_action(1, "quote_ask", 0, 8), _action(2, "quote_bid", 0, 12)],
    },
    {
        "name": "resting_bid_hit_by_crossing_ask",
        "inventories": DEAL_8,
        "goalSuitIdx": 0,
        "steps": [_action(1, "quote_bid", 0, 8), _action(2, "quote_ask", 0, 4)],
    },
    {
        "name": "trade_clears_all_suits_and_players",
        "inventories": DEAL_8,
        "goalSuitIdx": 0,
        "steps": [
            _action(0, "quote_bid", 0, 9),
            _action(2, "quote_ask", 3, 30),
            _action(3, "quote_bid", 1, 4),
            _action(1, "sell", 0),
        ],
    },
    {
        "name": "market_buy_into_empty_book",
        "inventories": DEAL_8,
        "goalSuitIdx": 0,
        "steps": [_action(0, "buy", 0)],
    },
    {
        "name": "same_player_quote_replacement",
        "inventories": DEAL_8,
        "goalSuitIdx": 0,
        "steps": [_action(0, "quote_bid", 0, 5), _action(0, "quote_bid", 0, 7)],
    },
    {
        "name": "tie_for_most_goal_cards_goal_has_eight",
        "inventories": DEAL_8,
        "goalSuitIdx": 0,
        "steps": [],
    },
    {
        "name": "goal_suit_has_ten_cards",
        "inventories": DEAL_10,
        "goalSuitIdx": 0,
        "steps": [],
    },
]


def _number(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _snapshot(env: SimpleFiggieEnv) -> dict[str, Any]:
    books = []
    for suit in range(env.num_suits):
        bid, bid_owner = env._best_bid(suit)
        ask, ask_owner = env._best_ask(suit)
        books.append(
            {
                "bid": {"price": _number(bid), "owner": bid_owner},
                "ask": {"price": _number(ask), "owner": ask_owner},
            }
        )
    return {
        "best": books,
        "inventories": env.inventories.astype(int).tolist(),
        "cash": env.cash.astype(float).tolist(),
        "lastTradePrice": env.last_trade_price.astype(float).tolist(),
        "trades": [
            {
                "buyerIdx": trade["buyer_idx"],
                "sellerIdx": trade["seller_idx"],
                "suit": trade["suit"],
                "price": float(trade["price"]),
                "aggressorSide": trade["aggressor_side"],
            }
            for trade in env._fixture_trades
        ],
    }


def _settlement(env: SimpleFiggieEnv, starting_cash: float) -> dict[str, Any]:
    goal_counts = env.inventories[:, env.goal_suit_idx].astype(int)
    card_payouts = goal_counts.astype(float) * env.config.goal_card_value
    pot = env.config.ante * env.config.num_players
    majority_pool = max(0.0, pot - float(card_payouts.sum()))
    max_count = int(goal_counts.max())
    winners = np.flatnonzero(goal_counts == max_count).tolist() if max_count > 0 else []
    shares = np.zeros(env.config.num_players, dtype=float)
    if winners:
        shares[winners] = majority_pool / len(winners)
    bankrolls = settle_round(
        inventories=env.inventories,
        cash=env.cash,
        goal_suit_idx=env.goal_suit_idx,
        goal_card_value=env.config.goal_card_value,
        goal_majority_bonus=env.config.goal_majority_bonus,
        total_pot=pot,
    )
    return {
        "goalSuitIdx": env.goal_suit_idx,
        "goalCardCounts": goal_counts.tolist(),
        "goalCardPayouts": card_payouts.tolist(),
        "majorityPool": majority_pool,
        "majorityShares": shares.tolist(),
        "winners": winners,
        "finalBankrolls": bankrolls.astype(float).tolist(),
        "profitFromStart": (bankrolls - starting_cash).astype(float).tolist(),
    }


def build_fixtures() -> dict[str, Any]:
    fixtures = []
    for scenario in SCENARIOS:
        starting_cash = float(scenario.get("startingCash", 350))
        ante = float(scenario.get("ante", 50))
        env = SimpleFiggieEnv(
            EnvConfig(
                market_mode="endogenous",
                quote_rules="official",
                starting_cash=starting_cash,
                ante=ante,
                max_steps=1,
            ),
            opponent_policies=[Hold(), Hold(), Hold()],
        )
        env.reset(seed=1)
        env._tie_break_start = 0
        env.inventories[:] = np.asarray(scenario["inventories"], dtype=np.int32)
        env.initial_inventories[:] = env.inventories
        env.cash[:] = starting_cash - ante
        env.goal_suit_idx = int(scenario["goalSuitIdx"])
        env._fixture_trades = []
        original_trade = env._trade

        def record_trade(buyer_idx, seller_idx, suit, price, by_quote_fill, aggressor_side):
            original_trade(buyer_idx, seller_idx, suit, price, by_quote_fill, aggressor_side)
            env._fixture_trades.append(
                {
                    "buyer_idx": int(buyer_idx),
                    "seller_idx": int(seller_idx),
                    "suit": int(suit),
                    "price": float(price),
                    "aggressor_side": aggressor_side,
                }
            )

        env._trade = record_trade
        steps = []
        for step in scenario["steps"]:
            action = step["action"]
            semantic_action = OpponentAction(
                action["kind"],
                suit=action["suit"],
                limit_price=action.get("price"),
            )
            env._apply_semantic_action(step["player"], semantic_action)
            steps.append(_snapshot(env))
        fixtures.append(
            {
                **scenario,
                "ante": ante,
                "startingCash": starting_cash,
                "expectedAfterSteps": steps,
                "expectedSettlement": _settlement(env, starting_cash),
            }
        )
    return {"schemaVersion": 1, "suits": ["spades", "clubs", "hearts", "diamonds"], "scenarios": fixtures}


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_fixtures(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
