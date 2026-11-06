"""Four opponents with distinct, recognisable Figgie playing styles.

Each style keys on a different information source, so they interact rather than
mirror one another:

- ``GoalHunter`` trusts its own hand and lifts offers to corner the goal suit.
- ``SpreadBanker`` quotes both sides around a fair value and earns the spread.
- ``TapeDetective`` waits, reads who is paying up on the public tape, then follows.
- ``Bluffer`` fakes demand in a decoy suit, sells into it, and accumulates quietly.

Endogenous quotes are absolute ``limit_price`` dollars. The browser arena
(``figgie_rl/arena/figgie_arena.js``) still mirrors the exogenous price levels
and does not know about ``limit_price``.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from figgie_rl.agents.baselines import OpponentAction, OpponentView

# Under pot-conserving settlement the majority holder takes the $200 pot minus
# $10 per goal card (8 or 10 cards), so roughly $100. Exogenous bots still use
# this constant. Endogenous prices use OFFICIAL_EXPECTED_REMAINDER instead.
DEFAULT_MAJORITY_BONUS = 100.0
DEFAULT_EDGE = 2.0
# The hunter bids inside the edge so its quote rises almost one-for-one with fair.
HUNTER_BID_EDGE = 1.0
PASSIVE_BID_FRACTION = 0.5
BLUFF_PASSIVE_FRACTION = 0.6
BLUFF_MAX_PRICE = 12.0
QUOTE_FLOOR = 1.0
QUOTE_CAP = 60.0
# Cards over which the expected pot remainder is spread while a bot is still short.
FAIR_TARGET_COUNT = 6


@lru_cache(maxsize=4096)
def _cached_posterior(hand: tuple[int, ...]) -> np.ndarray:
    # Imported lazily: figgie_rl.envs imports the agents package at load time.
    from figgie_rl.envs.mechanics import goal_suit_posterior

    return goal_suit_posterior(np.array(hand, dtype=np.int64)).astype(np.float64)


def hand_posterior(view: OpponentView) -> np.ndarray:
    """Goal-suit probabilities implied by the seat's original ten-card hand."""
    hand = view.initial_inventory if view.initial_inventory is not None else view.inventory
    try:
        return _cached_posterior(tuple(int(x) for x in hand)).copy()
    except ValueError:
        return np.full(len(hand), 1.0 / len(hand))


def others_flow(view: OpponentView) -> np.ndarray:
    """Net aggressive buying per suit by everyone else this round.

    The seat's own net inventory change is subtracted as an estimate of its own
    contribution to the public tape.
    """
    flow = view.cumulative_signed_flow
    if flow is None:
        flow = view.belief_flow
    own = np.zeros_like(flow)
    if view.initial_inventory is not None:
        own = (view.inventory - view.initial_inventory).astype(np.float64)
    return np.asarray(flow, dtype=np.float64) - own


def _round_fraction(view: OpponentView) -> float:
    return view.step / max(view.max_steps, 1)


def _missing_book() -> tuple[float, float]:
    from figgie_rl.envs.simple_figgie_env import MISSING_VIEW_ASK, MISSING_VIEW_BID

    return float(MISSING_VIEW_BID), float(MISSING_VIEW_ASK)


def _real_bid(view: OpponentView, suit: int) -> bool:
    missing_bid, _ = _missing_book()
    return float(view.best_bid[suit]) > missing_bid


def _real_ask(view: OpponentView, suit: int) -> bool:
    _, missing_ask = _missing_book()
    return float(view.best_ask[suit]) < missing_ask


def fair_value(
    belief: float,
    held: int,
    target_count: int,
    goal_card_value: float,
    remainder: float | None = None,
) -> float:
    """Dollar value of one more card of a suit believed to be goal with `belief`.

    While the seat is short of `target_count`, the card also carries an even
    slice of the expected pot remainder. After that it is worth face value only.
    """
    if remainder is None:
        from figgie_rl.envs.mechanics import OFFICIAL_EXPECTED_REMAINDER

        remainder = OFFICIAL_EXPECTED_REMAINDER
    per_card = float(goal_card_value)
    if held < target_count:
        per_card += float(remainder) / float(target_count)
    return float(belief) * per_card


def clip_quote(price: float, *, cash: float, is_bid: bool) -> float | None:
    """Clamp a quote to [$1, $60]. A bid above cash, or with cash under $1, is refused."""
    if is_bid:
        if cash < QUOTE_FLOOR:
            return None
        price = min(float(price), float(cash))
    price = float(np.clip(price, QUOTE_FLOOR, QUOTE_CAP))
    if is_bid and price > cash:
        return None
    return price


def _quote_bid(suit: int, price: float | None) -> OpponentAction:
    if price is None:
        return OpponentAction("hold")
    return OpponentAction("quote_bid", suit=suit, limit_price=float(price))


def _quote_ask(suit: int, price: float | None, inventory: int) -> OpponentAction:
    if price is None or inventory <= 0:
        return OpponentAction("hold")
    return OpponentAction("quote_ask", suit=suit, limit_price=float(price))


def pull_overpriced_bid(
    view: OpponentView,
    fair: np.ndarray,
    willingness: np.ndarray,
) -> OpponentAction | None:
    """Replace a resting bid that now pays more than the card is worth.

    A fill does not cancel the quote, and fair value drops once the seat is
    no longer short of the pot. Until the bid is replaced, other players can
    keep selling into the old price.
    """
    chosen: tuple[int, float] | None = None
    gap = 0.0
    for suit in range(len(fair)):
        resting = float(view.own_bid_quote[suit])
        if not np.isfinite(resting):
            continue
        ceiling = float(willingness[suit])
        own_ask = float(view.own_ask_quote[suit])
        crossed = np.isfinite(own_ask) and resting >= own_ask
        if crossed:
            ceiling = min(ceiling, own_ask - 1.0)
        over_fair = resting > float(fair[suit]) + 0.25
        if not over_fair and not crossed:
            continue
        if resting - ceiling > gap:
            gap = resting - ceiling
            chosen = (suit, ceiling)
    if chosen is None:
        return None
    suit, ceiling = chosen
    price = clip_quote(ceiling, cash=view.cash, is_bid=True)
    resting = float(view.own_bid_quote[suit])
    if price is None or price >= resting - 0.05:
        return None
    return OpponentAction("quote_bid", suit=suit, limit_price=float(price))


class GoalHunter:
    """Aggressive collector that corners its most likely goal suit."""

    def __init__(
        self,
        goal_card_value: float = 10.0,
        majority_bonus: float = DEFAULT_MAJORITY_BONUS,
        target_count: int = 6,
        dump_threshold: float = 0.15,
        edge: float = DEFAULT_EDGE,
    ) -> None:
        self.goal_card_value = float(goal_card_value)
        self.majority_bonus = float(majority_bonus)
        self.target_count = int(target_count)
        self.dump_threshold = float(dump_threshold)
        self.edge = float(edge)

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        if view.market_mode == "endogenous":
            return self._act_endogenous(view, rng)
        return self._act_exogenous(view, rng)

    def _act_exogenous(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        posterior = hand_posterior(view)
        target = int(np.argmax(posterior))
        held = int(view.inventory[target])

        # Each card short of a likely majority also buys a slice of the pot.
        bonus_share = self.majority_bonus / self.target_count if held < self.target_count else 0.0
        card_value = posterior[target] * (self.goal_card_value + bonus_share)
        ask = float(view.best_ask[target])
        if view.cash >= ask and ask <= card_value:
            return OpponentAction("buy", suit=target)

        # Fund the hunt by dumping suits it does not believe in.
        junk = [
            suit for suit in range(len(posterior))
            if suit != target and posterior[suit] < self.dump_threshold and view.inventory[suit] > 0
        ]
        if junk and rng.random() < 0.6:
            suit = max(junk, key=lambda s: int(view.inventory[s]))
            return OpponentAction("sell", suit=suit)
        return OpponentAction("quote_bid", suit=target, price_level=2)

    def _act_endogenous(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        posterior = hand_posterior(view)
        target = int(np.argmax(posterior))
        held = int(view.inventory[target])
        fair = fair_value(float(posterior[target]), held, self.target_count, self.goal_card_value)
        fair_by_suit = np.array(
            [
                fair_value(
                    float(posterior[suit]),
                    int(view.inventory[suit]),
                    self.target_count,
                    self.goal_card_value,
                )
                for suit in range(len(posterior))
            ]
        )
        willingness = np.zeros(len(posterior), dtype=np.float64)
        willingness[target] = float(fair_by_suit[target]) - HUNTER_BID_EDGE
        stale = pull_overpriced_bid(view, fair_by_suit, willingness)
        if stale is not None:
            return stale
        ask = float(view.best_ask[target])
        if _real_ask(view, target) and view.cash >= ask and ask <= fair:
            return OpponentAction("buy", suit=target)

        junk = [
            suit for suit in range(len(posterior))
            if suit != target and posterior[suit] < self.dump_threshold and view.inventory[suit] > 0
        ]
        if junk and rng.random() < 0.6:
            suit = max(junk, key=lambda s: int(view.inventory[s]))
            if _real_bid(view, suit):
                return OpponentAction("sell", suit=suit)
            junk_fair = fair_value(
                float(posterior[suit]),
                int(view.inventory[suit]),
                self.target_count,
                self.goal_card_value,
            )
            price = clip_quote(max(QUOTE_FLOOR, junk_fair + self.edge), cash=view.cash, is_bid=False)
            return _quote_ask(suit, price, int(view.inventory[suit]))
        bid = clip_quote(fair - HUNTER_BID_EDGE, cash=view.cash, is_bid=True)
        return _quote_bid(target, bid)


class SpreadBanker:
    """Market maker that quotes around posterior fair value and flattens inventory.

    ``edge`` is the endogenous half-spread and defaults to $2. Exogenous
    levels stay on the historical $1 edge so those actions do not move.
    """

    def __init__(
        self,
        goal_card_value: float = 10.0,
        edge: float = DEFAULT_EDGE,
        max_position: int = 3,
        inventory_skew: float = 0.5,
    ) -> None:
        self.goal_card_value = float(goal_card_value)
        self.edge = float(edge)
        self.max_position = int(max_position)
        self.inventory_skew = float(inventory_skew)

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        if view.market_mode == "endogenous":
            return self._act_endogenous(view, rng)
        return self._act_exogenous(view, rng)

    def _fair_endogenous(self, view: OpponentView) -> np.ndarray:
        posterior = hand_posterior(view)
        return np.array(
            [
                fair_value(
                    float(posterior[suit]),
                    int(view.inventory[suit]),
                    FAIR_TARGET_COUNT,
                    self.goal_card_value,
                )
                for suit in range(posterior.shape[0])
            ],
            dtype=np.float64,
        )

    def _act_exogenous(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        del rng
        num_suits = view.inventory.shape[0]
        fair = hand_posterior(view) * self.goal_card_value
        start = view.initial_inventory if view.initial_inventory is not None else view.inventory
        position = view.inventory.astype(np.float64) - start

        # Historical exogenous edge. Do not read self.edge here.
        level_edge = 1.0
        buy_gift = fair - view.best_ask
        buy_gift[view.best_ask > view.cash] = -np.inf
        if np.max(buy_gift) > 2.0 * level_edge:
            return OpponentAction("buy", suit=int(np.argmax(buy_gift)))
        sell_gift = view.best_bid - fair
        sell_gift[view.inventory <= 0] = -np.inf
        if np.max(sell_gift) > 2.0 * level_edge:
            return OpponentAction("sell", suit=int(np.argmax(sell_gift)))

        # Rotate through suits, alternating sides; skip any side or suit with no edge.
        bid_first = (view.step // num_suits) % 2 == 0
        for offset in range(num_suits):
            suit = (view.step + offset) % num_suits
            for side in (("bid", "ask") if bid_first else ("ask", "bid")):
                action = self._quote(view, suit, side, fair[suit], position[suit], level_edge)
                if action is not None:
                    return action
        return OpponentAction("hold")

    def _act_endogenous(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        del rng
        num_suits = view.inventory.shape[0]
        fair = self._fair_endogenous(view)
        start = view.initial_inventory if view.initial_inventory is not None else view.inventory
        position = view.inventory.astype(np.float64) - start

        buy_gift = fair - view.best_ask.astype(np.float64)
        for suit in range(num_suits):
            if not _real_ask(view, suit) or view.best_ask[suit] > view.cash:
                buy_gift[suit] = -np.inf
        if np.max(buy_gift) > 2.0 * self.edge:
            return OpponentAction("buy", suit=int(np.argmax(buy_gift)))
        sell_gift = view.best_bid.astype(np.float64) - fair
        for suit in range(num_suits):
            if not _real_bid(view, suit) or view.inventory[suit] <= 0:
                sell_gift[suit] = -np.inf
        if np.max(sell_gift) > 2.0 * self.edge:
            return OpponentAction("sell", suit=int(np.argmax(sell_gift)))

        willingness = np.array(
            [
                self._sided_prices(view, suit, float(fair[suit]), float(position[suit]))[0] or 0.0
                for suit in range(num_suits)
            ]
        )
        stale = pull_overpriced_bid(view, fair, willingness)
        if stale is not None:
            return stale

        bid_first = (view.step // num_suits) % 2 == 0
        for offset in range(num_suits):
            suit = (view.step + offset) % num_suits
            for side in (("bid", "ask") if bid_first else ("ask", "bid")):
                action = self._quote_endogenous(view, suit, side, float(fair[suit]), float(position[suit]))
                if action is not None:
                    return action
        return OpponentAction("hold")

    def _quote(
        self,
        view: OpponentView,
        suit: int,
        side: str,
        fair: float,
        position: float,
        level_edge: float,
    ) -> OpponentAction | None:
        skew = -self.inventory_skew * position
        if side == "bid":
            if position >= self.max_position:
                return None
            target = fair - level_edge + skew
            level = int(np.clip(np.floor(target - view.best_bid[suit]) + 1, 0, 2))
            if view.best_bid[suit] + level - 1 > target:
                return None
            return OpponentAction("quote_bid", suit=suit, price_level=level)
        if view.inventory[suit] <= 0 or position <= -self.max_position:
            return None
        target = fair + level_edge + skew
        level = int(np.clip(np.ceil(target - view.best_ask[suit]) + 1, 0, 2))
        return OpponentAction("quote_ask", suit=suit, price_level=level)

    def _sided_prices(
        self, view: OpponentView, suit: int, fair: float, position: float
    ) -> tuple[float | None, float | None]:
        """Bid and ask this seat would post, or None when that side is refused."""
        skew = -self.inventory_skew * position
        bid: float | None = None
        ask: float | None = None
        if position < self.max_position:
            bid = clip_quote(fair - self.edge + skew, cash=view.cash, is_bid=True)
        if int(view.inventory[suit]) > 0 and position > -self.max_position:
            ask = clip_quote(fair + self.edge + skew, cash=view.cash, is_bid=False)
        if bid is not None and ask is not None and bid >= ask:
            pulled = ask - 1.0
            bid = pulled if QUOTE_FLOOR <= pulled <= view.cash else None
        resting_ask = float(view.own_ask_quote[suit])
        resting_bid = float(view.own_bid_quote[suit])
        if bid is not None and np.isfinite(resting_ask) and bid >= resting_ask:
            bid = None
        if ask is not None and np.isfinite(resting_bid) and ask <= resting_bid:
            ask = None
        return bid, ask

    def _quote_endogenous(
        self, view: OpponentView, suit: int, side: str, fair: float, position: float
    ) -> OpponentAction | None:
        bid, ask = self._sided_prices(view, suit, fair, position)
        if side == "bid":
            if bid is None:
                return None
            return OpponentAction("quote_bid", suit=suit, limit_price=bid)
        if ask is None:
            return None
        return OpponentAction("quote_ask", suit=suit, limit_price=ask)


class TapeDetective:
    """Patient tape reader that updates its goal belief from others' aggressive trades."""

    def __init__(
        self,
        goal_card_value: float = 10.0,
        majority_bonus: float = DEFAULT_MAJORITY_BONUS,
        flow_weight: float = 0.35,
        confidence: float = 0.55,
        patience: float = 0.2,
        edge: float = DEFAULT_EDGE,
    ) -> None:
        self.goal_card_value = float(goal_card_value)
        self.majority_bonus = float(majority_bonus)
        self.flow_weight = float(flow_weight)
        self.confidence = float(confidence)
        self.patience = float(patience)
        self.edge = float(edge)

    def belief(self, view: OpponentView) -> np.ndarray:
        evidence = np.exp(self.flow_weight * np.clip(others_flow(view), -10.0, 10.0))
        posterior = hand_posterior(view) * evidence
        return posterior / posterior.sum()

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        if view.market_mode == "endogenous":
            return self._act_endogenous(view, rng)
        return self._act_exogenous(view, rng)

    def _act_exogenous(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        posterior = self.belief(view)
        target = int(np.argmax(posterior))
        certainty = float(posterior[target])

        ruled_out = [
            suit for suit in range(len(posterior))
            if suit != target and posterior[suit] < 0.05 and view.inventory[suit] > 0
        ]
        if _round_fraction(view) < self.patience or certainty < self.confidence:
            # Still gathering evidence: shed suits the tape rules out, bid quietly on the leader.
            if ruled_out and rng.random() < 0.3:
                return OpponentAction("sell", suit=ruled_out[0])
            if rng.random() < 0.3:
                return OpponentAction("hold")
            return OpponentAction("quote_bid", suit=target, price_level=0)

        bonus_share = self.majority_bonus / 6.0 if view.inventory[target] < 6 else 0.0
        value = certainty * (self.goal_card_value + bonus_share)
        ask = float(view.best_ask[target])
        if view.cash >= ask and ask <= value:
            return OpponentAction("buy", suit=target)
        if ruled_out:
            return OpponentAction("sell", suit=ruled_out[0])
        return OpponentAction("quote_bid", suit=target, price_level=1)

    def _suit_fair(self, belief: np.ndarray, view: OpponentView, suit: int) -> float:
        return fair_value(
            float(belief[suit]),
            int(view.inventory[suit]),
            FAIR_TARGET_COUNT,
            self.goal_card_value,
        )

    def _passive_or_firm_bid(
        self, view: OpponentView, suit: int, belief: np.ndarray, *, passive: bool
    ) -> OpponentAction:
        fair = self._suit_fair(belief, view, suit)
        raw = PASSIVE_BID_FRACTION * fair if passive else fair - self.edge
        return _quote_bid(suit, clip_quote(raw, cash=view.cash, is_bid=True))

    def _shed(self, view: OpponentView, suit: int, belief: np.ndarray) -> OpponentAction:
        """Ask near fair on a ruled-out suit. Hit a bid only when it pays that ask."""
        if int(view.inventory[suit]) <= 0:
            return OpponentAction("hold")
        ask_px = clip_quote(
            max(QUOTE_FLOOR, self._suit_fair(belief, view, suit) + self.edge),
            cash=view.cash,
            is_bid=False,
        )
        if ask_px is not None and _real_bid(view, suit) and float(view.best_bid[suit]) >= ask_px:
            return OpponentAction("sell", suit=suit)
        return _quote_ask(suit, ask_px, int(view.inventory[suit]))

    def _act_endogenous(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        posterior = self.belief(view)
        target = int(np.argmax(posterior))
        certainty = float(posterior[target])
        ruled_out = [
            suit for suit in range(len(posterior))
            if suit != target and posterior[suit] < 0.05 and view.inventory[suit] > 0
        ]
        gathering = _round_fraction(view) < self.patience or certainty < self.confidence
        fair_by_suit = np.array(
            [self._suit_fair(posterior, view, suit) for suit in range(len(posterior))]
        )
        willingness = np.zeros(len(posterior), dtype=np.float64)
        raw = PASSIVE_BID_FRACTION * fair_by_suit[target] if gathering else fair_by_suit[target] - self.edge
        willingness[target] = raw
        stale = pull_overpriced_bid(view, fair_by_suit, willingness)
        if stale is not None:
            return stale
        if gathering:
            if ruled_out and rng.random() < 0.3:
                return self._shed(view, ruled_out[0], posterior)
            if rng.random() < 0.3:
                return OpponentAction("hold")
            return self._passive_or_firm_bid(view, target, posterior, passive=True)

        value = self._suit_fair(posterior, view, target)
        ask = float(view.best_ask[target])
        if _real_ask(view, target) and view.cash >= ask and ask <= value:
            return OpponentAction("buy", suit=target)
        if ruled_out:
            return self._shed(view, ruled_out[0], posterior)
        return self._passive_or_firm_bid(view, target, posterior, passive=False)


class Bluffer:
    """Fakes demand in a decoy suit, sells into it, and accumulates its real target quietly."""

    def __init__(
        self,
        goal_card_value: float = 10.0,
        decoy_cards: int = 3,
        bluff_phase: float = 0.3,
        fade_threshold: float = 2.0,
        edge: float = DEFAULT_EDGE,
        bluff_max_price: float = BLUFF_MAX_PRICE,
    ) -> None:
        self.goal_card_value = float(goal_card_value)
        self.decoy_cards = int(decoy_cards)
        self.bluff_phase = float(bluff_phase)
        self.fade_threshold = float(fade_threshold)
        self.edge = float(edge)
        self.bluff_max_price = float(bluff_max_price)

    @staticmethod
    def decoy_suit(posterior: np.ndarray, target: int) -> int:
        """The suit it believes in least, which makes the cheapest convincing fake."""
        masked = posterior.copy()
        masked[target] = np.inf
        return int(np.argmin(masked))

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        if view.market_mode == "endogenous":
            return self._act_endogenous(view, rng)
        return self._act_exogenous(view, rng)

    def _act_exogenous(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        posterior = hand_posterior(view)
        target = int(np.argmax(posterior))
        decoy = self.decoy_suit(posterior, target)
        fraction = _round_fraction(view)
        start = view.initial_inventory if view.initial_inventory is not None else view.inventory

        if fraction < self.bluff_phase:
            # Loud: lift offers in the decoy so the tape shows conviction.
            bought = int(view.inventory[decoy] - start[decoy])
            if bought < self.decoy_cards and view.cash >= view.best_ask[decoy] and rng.random() < 0.6:
                return OpponentAction("buy", suit=decoy)
            return OpponentAction("quote_bid", suit=target, price_level=0)

        # Fade whoever is chasing a suit it does not believe in.
        flow = others_flow(view)
        fades = [
            suit for suit in range(len(posterior))
            if suit != target and flow[suit] >= self.fade_threshold and view.inventory[suit] > 0
        ]
        if fades and rng.random() < 0.5:
            return OpponentAction("sell", suit=max(fades, key=lambda s: flow[s]))

        # Unload the decoy high while the bluff lingers, then at the bid late on.
        if view.inventory[decoy] > 0 and rng.random() < 0.5:
            if fraction > 0.7:
                return OpponentAction("sell", suit=decoy)
            return OpponentAction("quote_ask", suit=decoy, price_level=2)

        # Never lifts offers in its real suit until the closing minutes.
        ask = float(view.best_ask[target])
        if fraction > 0.85 and view.cash >= ask and ask <= posterior[target] * self.goal_card_value:
            return OpponentAction("buy", suit=target)
        return OpponentAction("quote_bid", suit=target, price_level=1)

    def _target_bid(
        self, view: OpponentView, target: int, posterior: np.ndarray, *, aggressive: bool
    ) -> OpponentAction:
        fair = fair_value(
            float(posterior[target]),
            int(view.inventory[target]),
            FAIR_TARGET_COUNT,
            self.goal_card_value,
        )
        raw = fair - self.edge if aggressive else BLUFF_PASSIVE_FRACTION * fair
        return _quote_bid(target, clip_quote(raw, cash=view.cash, is_bid=True))

    def _decoy_ask(self, view: OpponentView, decoy: int, posterior: np.ndarray) -> OpponentAction:
        if int(view.inventory[decoy]) <= 0:
            return OpponentAction("hold")
        fair = fair_value(
            float(posterior[decoy]),
            int(view.inventory[decoy]),
            FAIR_TARGET_COUNT,
            self.goal_card_value,
        )
        last = float(view.last_trade_price[decoy])
        raw = max(fair + self.edge, last + 2.0)
        price = clip_quote(raw, cash=view.cash, is_bid=False)
        return _quote_ask(decoy, price, int(view.inventory[decoy]))

    def _act_endogenous(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        posterior = hand_posterior(view)
        target = int(np.argmax(posterior))
        decoy = self.decoy_suit(posterior, target)
        fraction = _round_fraction(view)
        start = view.initial_inventory if view.initial_inventory is not None else view.inventory
        fair_by_suit = np.array(
            [
                fair_value(
                    float(posterior[suit]),
                    int(view.inventory[suit]),
                    FAIR_TARGET_COUNT,
                    self.goal_card_value,
                )
                for suit in range(len(posterior))
            ]
        )
        willingness = np.zeros(len(posterior), dtype=np.float64)
        raw = (
            fair_by_suit[target] - self.edge
            if fraction > 0.85
            else BLUFF_PASSIVE_FRACTION * fair_by_suit[target]
        )
        willingness[target] = float(raw)
        stale = pull_overpriced_bid(view, fair_by_suit, willingness)
        if stale is not None:
            return stale

        if fraction < self.bluff_phase:
            bought = int(view.inventory[decoy] - start[decoy])
            ask = float(view.best_ask[decoy])
            can_lift = (
                bought < self.decoy_cards
                and _real_ask(view, decoy)
                and ask <= self.bluff_max_price
                and view.cash >= ask
            )
            if can_lift and rng.random() < 0.6:
                return OpponentAction("buy", suit=decoy)
            return self._target_bid(view, target, posterior, aggressive=False)

        flow = others_flow(view)
        fades = [
            suit for suit in range(len(posterior))
            if suit != target and flow[suit] >= self.fade_threshold and view.inventory[suit] > 0
        ]
        if fades and rng.random() < 0.5:
            suit = max(fades, key=lambda s: flow[s])
            if _real_bid(view, suit):
                return OpponentAction("sell", suit=suit)
            return OpponentAction("hold")

        if view.inventory[decoy] > 0 and rng.random() < 0.5:
            if fraction > 0.7 and _real_bid(view, decoy):
                return OpponentAction("sell", suit=decoy)
            return self._decoy_ask(view, decoy, posterior)

        ask = float(view.best_ask[target])
        if (
            fraction > 0.85
            and _real_ask(view, target)
            and view.cash >= ask
            and ask <= posterior[target] * self.goal_card_value
        ):
            return OpponentAction("buy", suit=target)
        return self._target_bid(view, target, posterior, aggressive=fraction > 0.85)
