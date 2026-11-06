"""Scripted baseline opponents for the simplified Figgie environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np

# Curriculum / per-opponent difficulty (player indices 1..N-1 vs the learning agent at 0).
OPPONENT_DIFFICULTY_CHOICES: Final[frozenset[str]] = frozenset(
    {
        "weak",
        "average",
        "tough",
        "bayesian",
        "hunter",
        "banker",
        "detective",
        "bluffer",
        "naive",
        "reservation",
    }
)
# Opponents with distinct personalities, implemented in figgie_rl.agents.styles.
PLAYING_STYLES: Final[tuple[str, ...]] = ("hunter", "banker", "detective", "bluffer")
OPPONENT_DIFFICULTY_SCORE: Final[dict[str, int]] = {
    "weak": 0,
    "average": 1,
    "tough": 2,
    "bayesian": 2,
    "hunter": 2,
    "banker": 1,
    "detective": 2,
    "bluffer": 2,
    "naive": 1,
    "reservation": 2,
}


@dataclass(frozen=True)
class OpponentView:
    """Public market state + private inventory for one opponent."""

    inventory: np.ndarray
    cash: float
    best_bid: np.ndarray
    best_ask: np.ndarray
    own_bid_quote: np.ndarray
    own_ask_quote: np.ndarray
    last_trade_price: np.ndarray
    last_trade_signed_volume: np.ndarray
    belief_flow: np.ndarray
    time_remaining: float
    step: int
    max_steps: int
    initial_inventory: np.ndarray | None = None
    # Net aggressor volume per suit over the whole round (buys +1, sells -1).
    cumulative_signed_flow: np.ndarray | None = None
    # "exogenous" keeps the historical 3-level quotes. "endogenous" asks the
    # style bots to name an absolute dollar price.
    market_mode: str = "exogenous"
    bid_available: np.ndarray | None = None
    ask_available: np.ndarray | None = None


@dataclass(frozen=True)
class OpponentAction:
    """Semantic action for scripted policies."""

    kind: str
    suit: int | None = None
    price_level: int = 1
    # Absolute quote in dollars. When set, the endogenous market uses this
    # instead of the 3-level scripted schedule.
    limit_price: float | None = None


class BaselinePolicy(Protocol):
    """Interface for scripted baseline opponents."""

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        ...


class RandomTrader:
    """Randomized behavior with simple inventory/cash validity checks.

    In endogenous mode it still quotes through the legacy price shim and is not price-aware.
    """

    def __init__(self, *, hold_extra_prob: float = 0.0) -> None:
        """hold_extra_prob: extra probability of choosing hold (used for weak opponents)."""
        self.hold_extra_prob = float(hold_extra_prob)

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        if rng.random() < self.hold_extra_prob:
            return OpponentAction("hold")

        choices = [OpponentAction("hold")]

        for suit in range(view.inventory.shape[0]):
            choices.append(OpponentAction("quote_bid", suit=suit, price_level=int(rng.integers(0, 3))))
            choices.append(OpponentAction("quote_ask", suit=suit, price_level=int(rng.integers(0, 3))))

            if view.cash >= view.best_ask[suit]:
                choices.append(OpponentAction("buy", suit=suit))
            if view.inventory[suit] > 0:
                choices.append(OpponentAction("sell", suit=suit))

        return choices[int(rng.integers(0, len(choices)))]


class InventoryAwareMarketMaker:
    """Quotes and mean-reverts inventory toward zero across suits.

    In endogenous mode it still quotes through the legacy price shim and is not price-aware.
    """

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        total_inventory = int(np.sum(view.inventory))
        if total_inventory > 16:
            suit = int(np.argmax(view.inventory))
            if view.inventory[suit] > 0:
                return OpponentAction("sell", suit=suit)

        if total_inventory < 6 and view.cash >= np.min(view.best_ask):
            suit = int(np.argmin(view.best_ask))
            return OpponentAction("buy", suit=suit)

        suit = int(rng.integers(0, view.inventory.shape[0]))
        side = "quote_bid" if rng.random() < 0.5 else "quote_ask"
        return OpponentAction(side, suit=suit, price_level=1)


class RuleBasedValueTrader:
    """Buys discounted suits and sells expensive inventory-heavy suits.

    In endogenous mode it still quotes through the legacy price shim and is not price-aware.
    """

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        mid = (view.best_bid + view.best_ask) / 2.0
        cheap_suit = int(np.argmin(mid))
        rich_suit = int(np.argmax(mid))

        # Mix value-seeking with momentum from recent prints.
        momentum = view.last_trade_price - mid
        momentum_suit = int(np.argmax(momentum))

        if view.cash >= view.best_ask[cheap_suit] and rng.random() < 0.45:
            return OpponentAction("buy", suit=cheap_suit)

        if view.inventory[rich_suit] > 0 and rng.random() < 0.35:
            return OpponentAction("sell", suit=rich_suit)

        if view.cash >= view.best_ask[momentum_suit] and rng.random() < 0.2:
            return OpponentAction("buy", suit=momentum_suit)

        quote_side = "quote_bid" if rng.random() < 0.5 else "quote_ask"
        quote_suit = cheap_suit if quote_side == "quote_bid" else rich_suit
        return OpponentAction(quote_side, suit=quote_suit, price_level=int(rng.integers(0, 3)))


class BayesianGoalTrader:
    """Trade using the exact goal-suit posterior implied by the initial hand."""

    def __init__(self, goal_card_value: float = 10.0, majority_bonus: float = 40.0) -> None:
        self.goal_card_value = float(goal_card_value)
        self.majority_bonus = float(majority_bonus)

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        from figgie_rl.envs.mechanics import goal_suit_posterior

        del rng
        hand = view.initial_inventory if view.initial_inventory is not None else view.inventory
        posterior = goal_suit_posterior(hand)
        expected_values = np.array(
            [
                probability
                * (
                    self.goal_card_value
                    + self.majority_bonus / max(2.0, float(view.inventory[suit] + 1))
                )
                for suit, probability in enumerate(posterior)
            ],
            dtype=np.float64,
        )

        buy_surplus = expected_values - view.best_ask
        buy_surplus[view.best_ask > view.cash] = -np.inf
        buy_suit = int(np.argmax(buy_surplus))
        if buy_surplus[buy_suit] > 0.0:
            return OpponentAction("buy", suit=buy_suit)

        sell_surplus = view.best_bid - expected_values
        sell_surplus[view.inventory <= 0] = -np.inf
        sell_suit = int(np.argmax(sell_surplus))
        if sell_surplus[sell_suit] > 0.0:
            return OpponentAction("sell", suit=sell_suit)
        return OpponentAction("hold")


class NaiveGoalBuyer:
    """Lift the ask in the hand's most likely goal suit, at any finite price.

    This is the strategy that collects a mechanical edge when an outside book
    offers every suit near $5 and a goal card pays $10. It does not post a
    reservation price and it does not read the tape. Use it as a diagnostic
    that the market, rather than a learned policy, is or is not giving that edge away.
    """

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        from figgie_rl.envs.mechanics import goal_suit_posterior

        del rng
        hand = view.initial_inventory if view.initial_inventory is not None else view.inventory
        posterior = goal_suit_posterior(hand)
        target = int(np.argmax(posterior))
        ask = float(view.best_ask[target])
        if np.isfinite(ask) and view.cash >= ask:
            return OpponentAction("buy", suit=target)
        # No offer to lift. Bid the aggressive scripted rung so a willing
        # holder can sell. The endogenous market maps that rung to $20.
        return OpponentAction("quote_bid", suit=target, price_level=2)


class ReservationMarketMaker:
    """Quote a hand-computed reservation and cross only for a clear edge.

    Fair value is posterior times ($10 face plus an even slice of the expected
    pot remainder). This opponent will not sell a likely goal card at the old
    outside price. It exists so the diagnostic can separate "there is no
    outside book" from "nobody is willing to trade."
    """

    def __init__(self, edge: float = 2.0, majority_cards: float = 6.0) -> None:
        self.edge = float(edge)
        self.majority_cards = float(majority_cards)

    def _fair(self, view: OpponentView) -> np.ndarray:
        from figgie_rl.envs.mechanics import (
            OFFICIAL_EXPECTED_REMAINDER,
            OFFICIAL_GOAL_CARD_VALUE,
            goal_suit_posterior,
        )

        hand = view.initial_inventory if view.initial_inventory is not None else view.inventory
        posterior = goal_suit_posterior(hand)
        per_card_bonus = OFFICIAL_EXPECTED_REMAINDER / self.majority_cards
        return posterior * (OFFICIAL_GOAL_CARD_VALUE + per_card_bonus)

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        fair = self._fair(view)
        buy_edge = fair - view.best_ask
        buy_edge[view.best_ask > view.cash] = -np.inf
        buy_suit = int(np.argmax(buy_edge))
        if np.isfinite(buy_edge[buy_suit]) and buy_edge[buy_suit] > self.edge:
            return OpponentAction("buy", suit=buy_suit)

        sell_edge = view.best_bid - fair
        sell_edge[view.inventory <= 0] = -np.inf
        sell_suit = int(np.argmax(sell_edge))
        if np.isfinite(sell_edge[sell_suit]) and sell_edge[sell_suit] > self.edge:
            return OpponentAction("sell", suit=sell_suit)

        suit = int(view.step + int(rng.integers(0, fair.shape[0]))) % int(fair.shape[0])
        if rng.random() < 0.5:
            price = max(1.0, float(fair[suit] - self.edge))
            if view.cash < price:
                return OpponentAction("hold")
            return OpponentAction("quote_bid", suit=suit, limit_price=price)
        if int(view.inventory[suit]) <= 0:
            return OpponentAction("hold")
        return OpponentAction(
            "quote_ask",
            suit=suit,
            limit_price=float(fair[suit] + self.edge),
        )


def policy_for_difficulty(level: str) -> BaselinePolicy:
    """Map a curriculum label to a scripted policy (weak → random, average → MM, tough → value)."""
    if level == "weak":
        return RandomTrader(hold_extra_prob=0.35)
    if level == "average":
        return InventoryAwareMarketMaker()
    if level == "tough":
        return RuleBasedValueTrader()
    if level == "bayesian":
        return BayesianGoalTrader()
    if level == "naive":
        return NaiveGoalBuyer()
    if level == "reservation":
        return ReservationMarketMaker()
    if level in PLAYING_STYLES:
        from figgie_rl.agents import styles

        return {
            "hunter": styles.GoalHunter,
            "banker": styles.SpreadBanker,
            "detective": styles.TapeDetective,
            "bluffer": styles.Bluffer,
        }[level]()
    raise ValueError(
        f"Unknown opponent difficulty {level!r}; expected one of {sorted(OPPONENT_DIFFICULTY_CHOICES)}"
    )


def policies_from_difficulties(difficulties: tuple[str, ...]) -> list[BaselinePolicy]:
    """Build one scripted opponent policy per seat (same order as env opponent indices 1, 2, …)."""
    return [policy_for_difficulty(d) for d in difficulties]
