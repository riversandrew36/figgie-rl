"""Core deterministic mechanics for simplified Figgie rounds."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from math import comb, prod

import numpy as np

SUITS = ("spades", "clubs", "hearts", "diamonds")
SUIT_TO_INDEX = {suit: idx for idx, suit in enumerate(SUITS)}
INDEX_TO_SUIT = {idx: suit for suit, idx in SUIT_TO_INDEX.items()}
# Official Figgie (https://www.figgie.com/how-to-play): four players start with $350,
# each antes $50 into a $200 pot, each goal card pays $10 from that pot, and the
# player or players with the most goal cards split the remainder. The goal suit
# has 8 cards (remainder $120) or 10 cards (remainder $100). It never has 12.
OFFICIAL_STARTING_CASH = 350.0
OFFICIAL_ANTE = 50.0
OFFICIAL_POT = 200.0
OFFICIAL_GOAL_CARD_VALUE = 10.0
# The color partner of the 12-card suit is equally likely to be any of the
# other three count slots, so the goal suit has 8 cards with probability 1/3
# and 10 cards with probability 2/3. Remainders are $120 and $100.
OFFICIAL_EXPECTED_REMAINDER = (120.0 + 100.0 + 100.0) / 3.0

SUIT_COLORS = {
    "spades": "black",
    "clubs": "black",
    "hearts": "red",
    "diamonds": "red",
}
COLOR_PAIR = {
    "spades": "clubs",
    "clubs": "spades",
    "hearts": "diamonds",
    "diamonds": "hearts",
}


@dataclass(frozen=True)
class DealResult:
    """Cards and hidden goal metadata for a single round."""

    inventories: np.ndarray
    suit_distribution: np.ndarray
    heavy_suit_idx: int
    goal_suit_idx: int


def draw_suit_distribution(rng: np.random.Generator) -> np.ndarray:
    """Sample a suit distribution by assigning 12/10/10/8 across suits."""
    counts = np.array([12, 10, 10, 8], dtype=np.int32)
    return rng.permutation(counts)


def infer_goal_suit_from_heavy(heavy_suit_idx: int) -> int:
    """Goal suit is the same-color partner of the heavy suit."""
    heavy_suit = INDEX_TO_SUIT[heavy_suit_idx]
    goal_suit = COLOR_PAIR[heavy_suit]
    return SUIT_TO_INDEX[goal_suit]


def goal_suit_posterior(hand_inventory: np.ndarray) -> np.ndarray:
    """Return the exact prior posterior over goal suits given a 10-card hand.

    The deck distribution is a uniform random permutation of 12/10/10/8.
    A heavy suit is the suit with 12 cards; the goal is its same-color partner.
    This uses only the player's private initial hand and does not reveal the
    round's hidden metadata.
    """
    hand = np.asarray(hand_inventory, dtype=np.int64)
    if hand.shape != (len(SUITS),) or np.any(hand < 0) or int(hand.sum()) != 10:
        raise ValueError("hand_inventory must contain four nonnegative counts totaling 10")

    posterior = np.zeros(len(SUITS), dtype=np.float64)
    remaining_distribution = (10, 10, 8)
    for heavy_suit in range(len(SUITS)):
        other_suits = [suit for suit in range(len(SUITS)) if suit != heavy_suit]
        likelihood = 0
        for remainder in permutations(remaining_distribution):
            deck_counts = [0] * len(SUITS)
            deck_counts[heavy_suit] = 12
            for suit, count in zip(other_suits, remainder):
                deck_counts[suit] = count
            likelihood += prod(comb(deck_count, int(hand[suit])) for suit, deck_count in enumerate(deck_counts))
        goal_suit = SUIT_TO_INDEX[COLOR_PAIR[INDEX_TO_SUIT[heavy_suit]]]
        posterior[goal_suit] += likelihood

    total = float(posterior.sum())
    if total <= 0.0:
        raise ValueError("hand_inventory is impossible under the configured deck")
    return (posterior / total).astype(np.float32)


def build_deck_from_distribution(suit_distribution: np.ndarray) -> np.ndarray:
    """Build a shuffled-ready deck of suit indices from suit counts."""
    cards: list[int] = []
    for suit_idx, count in enumerate(suit_distribution):
        cards.extend([suit_idx] * int(count))
    return np.array(cards, dtype=np.int32)


def deal_round(
    rng: np.random.Generator,
    num_players: int = 4,
    hand_size: int = 10,
) -> DealResult:
    """Deal cards and return each player's initial inventory by suit."""
    suit_distribution = draw_suit_distribution(rng)
    heavy_suit_idx = int(np.argmax(suit_distribution))
    goal_suit_idx = infer_goal_suit_from_heavy(heavy_suit_idx)

    deck = build_deck_from_distribution(suit_distribution)
    rng.shuffle(deck)

    cards_needed = num_players * hand_size
    if cards_needed != deck.size:
        raise ValueError(
            f"Simplified environment requires exact deck use: "
            f"{cards_needed=} and {deck.size=}."
        )

    hands = deck.reshape(num_players, hand_size)
    inventories = np.zeros((num_players, len(SUITS)), dtype=np.int32)
    for player in range(num_players):
        counts = np.bincount(hands[player], minlength=len(SUITS))
        inventories[player] = counts

    return DealResult(
        inventories=inventories,
        suit_distribution=suit_distribution,
        heavy_suit_idx=heavy_suit_idx,
        goal_suit_idx=goal_suit_idx,
    )


def settle_round(
    inventories: np.ndarray,
    cash: np.ndarray,
    goal_suit_idx: int,
    goal_card_value: float = 10.0,
    goal_majority_bonus: float = 40.0,
    total_pot: float | None = None,
) -> np.ndarray:
    """Return final bankroll after valuing goal suit and majority bonus."""
    bankroll = cash.astype(np.float64).copy()
    goal_counts = inventories[:, goal_suit_idx].astype(np.float64)
    bankroll += goal_counts * goal_card_value

    majority_bonus = goal_majority_bonus
    if total_pot is not None:
        card_payout = float(np.sum(goal_counts) * goal_card_value)
        majority_bonus = max(0.0, float(total_pot) - card_payout)

    max_goal = np.max(goal_counts)
    winners = np.where(goal_counts == max_goal)[0]
    if max_goal > 0 and winners.size > 0:
        bankroll[winners] += majority_bonus / float(winners.size)

    return bankroll
