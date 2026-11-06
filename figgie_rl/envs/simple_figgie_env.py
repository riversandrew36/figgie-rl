"""Gymnasium environment for simplified Figgie RL training."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from figgie_rl.agents.baselines import (
    OPPONENT_DIFFICULTY_CHOICES,
    OPPONENT_DIFFICULTY_SCORE,
    BaselinePolicy,
    InventoryAwareMarketMaker,
    OpponentAction,
    OpponentView,
    RandomTrader,
    RuleBasedValueTrader,
    policies_from_difficulties,
)
from figgie_rl.envs.mechanics import SUITS, deal_round, goal_suit_posterior, settle_round

MARKET_MODES = ("exogenous", "endogenous")
# Absolute dollars. The rungs above $10 exist so a bid can pay for a share of
# the $100/$120 majority remainder, not only the $10 face value. $60 is a cap.
ENDOGENOUS_PRICE_LADDER: tuple[float, ...] = (
    1, 2, 4, 6, 8, 10, 12, 16, 20, 30, 40, 60,
)
# Scripted policies still emit price_level 0, 1, 2. Those three words mean
# passive / mid / aggressive and select these ladder indices. They are not
# offsets from an outside quote, because the endogenous market has none.
ENDOGENOUS_LEGACY_BID_RUNGS = (2, 5, 8)  # $4, $10, $20
ENDOGENOUS_LEGACY_ASK_RUNGS = (4, 6, 9)  # $8, $12, $30
# Shown to scripted bots when nobody is offering or bidding. Not an order.
MISSING_VIEW_BID = 0.0
MISSING_VIEW_ASK = 1.0e6


@dataclass(frozen=True)
class EnvConfig:
    max_steps: int = 120
    num_players: int = 4
    tick_size: float = 1.0
    base_spread: float = 2.0
    drift_std: float = 0.25
    external_fill_prob: float = 0.6
    external_order_flow_prob: float = 0.2
    goal_card_value: float = 10.0
    goal_majority_bonus: float = 40.0
    starting_cash: float = 350.0
    ante: float = 50.0
    pot_conserving_settlement: bool = True
    quote_ttl_steps: int = 8
    belief_flow_decay: float = 0.85
    include_belief_features: bool = False
    include_goal_belief_features: bool = False
    # exogenous: outside random-walk book and probabilistic forced fills.
    # endogenous: prices come only from player quotes; no forced trades.
    market_mode: str = "exogenous"
    seed: int | None = None
    # One label per scripted opponent: weak | average | tough | bayesian | hunter | banker | detective | bluffer
    opponent_difficulties: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        od = self.opponent_difficulties
        if od is None:
            tup = None
        else:
            tup = tuple(str(x) for x in od)
        n_opp = self.num_players - 1
        if tup is not None and len(tup) != n_opp:
            raise ValueError(
                f"opponent_difficulties must have length {n_opp} (num_players - 1), got {len(tup)}"
            )
        bad = [x for x in tup or () if x not in OPPONENT_DIFFICULTY_CHOICES]
        if bad:
            raise ValueError(
                f"Invalid opponent_difficulties labels {bad}; "
                f"allowed: {sorted(OPPONENT_DIFFICULTY_CHOICES)}"
            )
        object.__setattr__(self, "opponent_difficulties", tup)
        if self.starting_cash < 0 or self.ante < 0 or self.ante > self.starting_cash:
            raise ValueError("starting_cash and ante must satisfy 0 <= ante <= starting_cash")
        if self.quote_ttl_steps <= 0:
            raise ValueError("quote_ttl_steps must be > 0")
        if not 0.0 <= self.belief_flow_decay < 1.0:
            raise ValueError("belief_flow_decay must be in [0, 1)")
        if self.market_mode not in MARKET_MODES:
            raise ValueError(
                f"market_mode must be one of {MARKET_MODES}, got {self.market_mode!r}"
            )


def build_policy_observation(
    *,
    inventory: np.ndarray,
    cash: float,
    best_bid: np.ndarray,
    best_ask: np.ndarray,
    own_bid_quote: np.ndarray,
    own_ask_quote: np.ndarray,
    last_trade_price: np.ndarray,
    last_trade_signed_volume: np.ndarray,
    belief_flow: np.ndarray,
    time_remaining: float,
    step_fraction: float,
    include_belief_features: bool,
    initial_inventory: np.ndarray | None = None,
    include_goal_belief_features: bool = False,
    bid_available: np.ndarray | None = None,
    ask_available: np.ndarray | None = None,
) -> np.ndarray:
    """Encode the policy observation consistently for every player seat."""
    finite_bids = np.where(np.isfinite(own_bid_quote), own_bid_quote, 0.0)
    finite_asks = np.where(np.isfinite(own_ask_quote), own_ask_quote, 0.0)
    parts = [
        inventory.astype(np.float32) / 20.0,
        np.array([cash / 200.0], dtype=np.float32),
        best_bid.astype(np.float32) / 20.0,
        best_ask.astype(np.float32) / 20.0,
        finite_bids.astype(np.float32) / 20.0,
        finite_asks.astype(np.float32) / 20.0,
        last_trade_price.astype(np.float32) / 20.0,
        last_trade_signed_volume.astype(np.float32),
        np.array([time_remaining], dtype=np.float32),
        np.array([step_fraction], dtype=np.float32),
    ]
    if include_belief_features:
        clipped_flow = np.clip(belief_flow, -3.0, 3.0)
        belief = (clipped_flow - clipped_flow.min()) / (
            clipped_flow.max() - clipped_flow.min() + 1e-6
        )
        parts.append(belief.astype(np.float32))
    if include_goal_belief_features:
        if initial_inventory is None:
            initial_inventory = inventory
        parts.append(goal_suit_posterior(initial_inventory))
    if bid_available is not None and ask_available is not None:
        parts.append(np.asarray(bid_available, dtype=np.float32))
        parts.append(np.asarray(ask_available, dtype=np.float32))
    return np.concatenate(parts).astype(np.float32)


class SimpleFiggieEnv(gym.Env[np.ndarray, int]):
    """Single-learning-agent simplified Figgie market simulation."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        config: EnvConfig | None = None,
        opponent_policies: list[BaselinePolicy] | None = None,
    ) -> None:
        super().__init__()
        self.config = config or EnvConfig()
        self.num_suits = len(SUITS)
        self.agent_idx = 0
        self.opponent_seats = [1, 2, 3]
        self._tie_break_start = 0
        self._action_order_start = 0

        if self.config.num_players != 4:
            raise ValueError(
                "This simplified environment currently supports exactly 4 players."
            )
        if self.config.max_steps <= 0:
            raise ValueError("max_steps must be > 0")

        if opponent_policies is None:
            if self.config.opponent_difficulties is not None:
                opponent_policies = policies_from_difficulties(self.config.opponent_difficulties)
                self._opponent_difficulty_labels: list[str] | None = list(
                    self.config.opponent_difficulties
                )
            else:
                opponent_policies = [
                    RandomTrader(),
                    InventoryAwareMarketMaker(),
                    RuleBasedValueTrader(),
                ]
                self._opponent_difficulty_labels = ["weak", "average", "tough"]
        else:
            self._opponent_difficulty_labels = None
        if len(opponent_policies) != self.config.num_players - 1:
            raise ValueError(
                "opponent_policies length must equal num_players - 1"
            )
        self.opponent_policies = opponent_policies

        self._action_table = self.build_action_table(
            self.num_suits, market_mode=self.config.market_mode
        )
        self.action_space = spaces.Discrete(len(self._action_table))

        obs_dim = (self.num_suits * 7) + 3
        if self.config.include_belief_features:
            obs_dim += self.num_suits
        if self.config.include_goal_belief_features:
            obs_dim += self.num_suits
        if self.config.market_mode == "endogenous":
            obs_dim += 2 * self.num_suits
        self.observation_space = spaces.Box(
            low=-10.0,
            high=10.0,
            shape=(obs_dim,),
            dtype=np.float32,
        )

        self.np_random = np.random.default_rng(self.config.seed)
        self._reset_state()

    def _reset_state(self) -> None:
        self.current_step = 0
        self.goal_suit_idx = 0
        self.heavy_suit_idx = 0
        self.suit_distribution = np.array([10, 10, 10, 10], dtype=np.int32)

        self.inventories = np.zeros((self.config.num_players, self.num_suits), dtype=np.int32)
        self.initial_inventories = np.zeros_like(self.inventories)
        self.cash = np.full(
            self.config.num_players,
            self.config.starting_cash - self.config.ante,
            dtype=np.float64,
        )

        self.external_bid = np.full(self.num_suits, 4.0, dtype=np.float64)
        self.external_ask = np.full(self.num_suits, 6.0, dtype=np.float64)
        self.fundamental_mid = np.full(self.num_suits, 5.0, dtype=np.float64)
        # Exogenous marks start at the outside mid. Endogenous marks stay at 0
        # until a player-to-player trade prints, so a phantom $5 does not
        # re-enter the reward through the back door.
        initial_print = 5.0 if self.config.market_mode == "exogenous" else 0.0
        self.last_trade_price = np.full(self.num_suits, initial_print, dtype=np.float64)
        self.last_trade_signed_volume = np.zeros(self.num_suits, dtype=np.float64)
        self.has_traded = np.zeros(self.num_suits, dtype=bool)
        self.belief_flow = np.zeros(self.num_suits, dtype=np.float64)
        self.cumulative_signed_flow = np.zeros(self.num_suits, dtype=np.float64)

        # Indexed by seat, not by "opponent slot". The learner's seat rotates,
        # and slot = seat - 1 collides once the learner leaves seat 0.
        self.bid_quotes = np.full(
            (self.config.num_players, self.num_suits), -np.inf, dtype=np.float64
        )
        self.ask_quotes = np.full(
            (self.config.num_players, self.num_suits), np.inf, dtype=np.float64
        )
        self.bid_quote_ages = np.full(
            (self.config.num_players, self.num_suits), -1, dtype=np.int32
        )
        self.ask_quote_ages = np.full(
            (self.config.num_players, self.num_suits), -1, dtype=np.int32
        )

        self.agent_trade_count = 0
        self.agent_quote_fill_count = 0
        self.agent_spread_capture = 0.0

    @property
    def observation_spec(self) -> dict[str, int]:
        spec = {
            "inventory_by_suit": self.num_suits,
            "cash": 1,
            "market_best_bid": self.num_suits,
            "market_best_ask": self.num_suits,
            "own_bid_quote": self.num_suits,
            "own_ask_quote": self.num_suits,
            "last_trade_price": self.num_suits,
            "last_trade_signed_volume": self.num_suits,
            "time_remaining": 1,
            "step_fraction": 1,
        }
        if self.config.include_belief_features:
            spec["belief_features"] = self.num_suits
        if self.config.include_goal_belief_features:
            spec["goal_suit_posterior"] = self.num_suits
        if self.config.market_mode == "endogenous":
            spec["bid_available"] = self.num_suits
            spec["ask_available"] = self.num_suits
        return spec

    @staticmethod
    def build_action_table(
        num_suits: int,
        market_mode: str = "exogenous",
    ) -> list[tuple[str, int | None, int | None]]:
        table: list[tuple[str, int | None, int | None]] = [("hold", None, None)]
        quote_levels = 3 if market_mode == "exogenous" else len(ENDOGENOUS_PRICE_LADDER)
        for suit in range(num_suits):
            for level in range(quote_levels):
                table.append(("quote_bid", suit, level))
            for level in range(quote_levels):
                table.append(("quote_ask", suit, level))
            table.append(("sell", suit, None))
            table.append(("buy", suit, None))
        return table

    @classmethod
    def decode_discrete_action(
        cls,
        action: int,
        num_suits: int,
        market_mode: str = "exogenous",
    ) -> OpponentAction:
        table = cls.build_action_table(num_suits, market_mode=market_mode)
        kind, suit, level = table[action]
        if (
            market_mode == "endogenous"
            and kind in {"quote_bid", "quote_ask"}
            and level is not None
        ):
            return OpponentAction(
                kind=kind,
                suit=suit,
                price_level=level,
                limit_price=float(ENDOGENOUS_PRICE_LADDER[level]),
            )
        return OpponentAction(kind=kind, suit=suit, price_level=1 if level is None else level)

    @classmethod
    def describe_action(
        cls,
        action: int,
        num_suits: int,
        market_mode: str = "exogenous",
    ) -> str:
        semantic = cls.decode_discrete_action(action, num_suits, market_mode=market_mode)
        if semantic.kind == "hold":
            return "hold"
        if semantic.kind in {"buy", "sell"}:
            return f"{semantic.kind} {SUITS[int(semantic.suit)]}"
        if semantic.limit_price is not None:
            return (
                f"{semantic.kind} {SUITS[int(semantic.suit)]} "
                f"price={semantic.limit_price:.0f}"
            )
        return (
            f"{semantic.kind} {SUITS[int(semantic.suit)]} "
            f"level={semantic.price_level}"
        )

    def _decode_agent_action(self, action: int) -> OpponentAction:
        return self.decode_discrete_action(
            action, self.num_suits, market_mode=self.config.market_mode
        )

    def encode_semantic_action(self, action: OpponentAction) -> int:
        """Map a scripted action onto this environment's discrete action table."""
        price_level = action.price_level
        if (
            self.config.market_mode == "endogenous"
            and action.kind in {"quote_bid", "quote_ask"}
        ):
            if action.limit_price is not None:
                ladder = np.asarray(ENDOGENOUS_PRICE_LADDER, dtype=np.float64)
                price_level = int(np.argmin(np.abs(ladder - float(action.limit_price))))
            else:
                rung_table = (
                    ENDOGENOUS_LEGACY_BID_RUNGS
                    if action.kind == "quote_bid"
                    else ENDOGENOUS_LEGACY_ASK_RUNGS
                )
                price_level = rung_table[int(np.clip(action.price_level, 0, 2))]
        for index, (kind, suit, level) in enumerate(self._action_table):
            if kind == action.kind and suit == action.suit and (
                kind not in {"quote_bid", "quote_ask"} or level == price_level
            ):
                return index
        raise ValueError(f"Policy returned unsupported action: {action}")

    def _quote_price(self, side: str, suit: int, level: int) -> float:
        if side == "quote_bid":
            return max(0.0, self.external_bid[suit] + self.config.tick_size * (level - 1))
        return max(0.0, self.external_ask[suit] + self.config.tick_size * (level - 1))

    def _resolve_quote_price(self, action: OpponentAction) -> float:
        if action.limit_price is not None:
            price = float(action.limit_price)
            if self.config.market_mode == "endogenous":
                price = float(np.clip(price, 1.0, ENDOGENOUS_PRICE_LADDER[-1]))
            return max(0.0, price)
        level = int(np.clip(action.price_level, 0, 2))
        if self.config.market_mode == "endogenous":
            rungs = (
                ENDOGENOUS_LEGACY_BID_RUNGS
                if action.kind == "quote_bid"
                else ENDOGENOUS_LEGACY_ASK_RUNGS
            )
            return float(ENDOGENOUS_PRICE_LADDER[rungs[level]])
        return self._quote_price(str(action.kind), int(action.suit), level)

    def _best_bid(self, suit: int, excluding_player: int | None = None) -> tuple[float, int | None]:
        if self.config.market_mode == "endogenous":
            best_price = -np.inf
            best_player = None
        else:
            best_price = float(self.external_bid[suit])
            best_player = None
        for offset in range(self.config.num_players):
            player_idx = (self._tie_break_start + offset) % self.config.num_players
            if excluding_player == player_idx:
                continue
            bid_quotes, _ = self._player_quotes(player_idx)
            quote = bid_quotes[suit]
            if quote > best_price:
                best_price = float(quote)
                best_player = player_idx

        return best_price, best_player

    def _best_ask(self, suit: int, excluding_player: int | None = None) -> tuple[float, int | None]:
        if self.config.market_mode == "endogenous":
            best_price = np.inf
            best_player = None
        else:
            best_price = float(self.external_ask[suit])
            best_player = None
        for offset in range(self.config.num_players):
            player_idx = (self._tie_break_start + offset) % self.config.num_players
            if excluding_player == player_idx:
                continue
            _, ask_quotes = self._player_quotes(player_idx)
            quote = ask_quotes[suit]
            if quote < best_price:
                best_price = float(quote)
                best_player = player_idx

        return best_price, best_player

    def _update_external_book(self) -> None:
        noise = self.np_random.normal(0.0, self.config.drift_std, size=self.num_suits)
        self.fundamental_mid = np.clip(self.fundamental_mid + noise, 1.0, 20.0)

        half_spread = self.config.base_spread / 2.0
        self.external_bid = np.maximum(0.0, self.fundamental_mid - half_spread)
        self.external_ask = self.fundamental_mid + half_spread

    def _book_arrays(
        self, excluding_player: int | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return observation prices, availability flags, and scripted-bot prices.

        Observation prices are 0 when that side of the book is empty so the
        network input stays bounded. Scripted bots instead see a missing bid
        as 0 and a missing ask as a non-finite-safe sentinel above any stack,
        so they do not treat an empty book as a free offer.
        """
        obs_bid = np.zeros(self.num_suits, dtype=np.float64)
        obs_ask = np.zeros(self.num_suits, dtype=np.float64)
        bid_available = np.zeros(self.num_suits, dtype=np.float32)
        ask_available = np.zeros(self.num_suits, dtype=np.float32)
        view_bid = np.zeros(self.num_suits, dtype=np.float64)
        view_ask = np.zeros(self.num_suits, dtype=np.float64)
        endogenous = self.config.market_mode == "endogenous"
        for suit in range(self.num_suits):
            bid, bid_owner = self._best_bid(suit, excluding_player=excluding_player)
            ask, ask_owner = self._best_ask(suit, excluding_player=excluding_player)
            bid_live = (not endogenous) or bid_owner is not None
            ask_live = (not endogenous) or ask_owner is not None
            if bid_live:
                obs_bid[suit] = bid
                view_bid[suit] = bid
                bid_available[suit] = 1.0
            else:
                view_bid[suit] = MISSING_VIEW_BID
            if ask_live:
                obs_ask[suit] = ask
                view_ask[suit] = ask
                ask_available[suit] = 1.0
            else:
                view_ask[suit] = MISSING_VIEW_ASK
        return obs_bid, obs_ask, bid_available, ask_available, view_bid, view_ask

    def _market_best_bid_vector(self, excluding_player: int | None = None) -> np.ndarray:
        return self._book_arrays(excluding_player)[0].astype(np.float32)

    def _market_best_ask_vector(self, excluding_player: int | None = None) -> np.ndarray:
        return self._book_arrays(excluding_player)[1].astype(np.float32)

    def _normalized_bid_quotes(self, quotes: np.ndarray) -> np.ndarray:
        finite_quotes = np.where(np.isfinite(quotes), quotes, 0.0)
        return (finite_quotes / 20.0).astype(np.float32)

    def _normalized_ask_quotes(self, quotes: np.ndarray) -> np.ndarray:
        finite_quotes = np.where(np.isfinite(quotes), quotes, 0.0)
        return (finite_quotes / 20.0).astype(np.float32)

    def _reference_prices(self) -> np.ndarray:
        if self.config.market_mode == "exogenous":
            return (self.external_bid + self.external_ask) / 2.0
        return np.where(self.has_traded, self.last_trade_price, 0.0)

    def _mark_to_market(self, player_idx: int) -> float:
        inventory_value = float(np.dot(self.inventories[player_idx], self._reference_prices()))
        return float(self.cash[player_idx] + inventory_value)

    @property
    def agent_bid_quote(self) -> np.ndarray:
        return self.bid_quotes[self.agent_idx]

    @property
    def agent_ask_quote(self) -> np.ndarray:
        return self.ask_quotes[self.agent_idx]

    @property
    def agent_bid_quote_age(self) -> np.ndarray:
        return self.bid_quote_ages[self.agent_idx]

    @property
    def agent_ask_quote_age(self) -> np.ndarray:
        return self.ask_quote_ages[self.agent_idx]

    def _player_quotes(self, player_idx: int) -> tuple[np.ndarray, np.ndarray]:
        return self.bid_quotes[player_idx], self.ask_quotes[player_idx]

    def _age_and_expire_quotes(self) -> None:
        quote_groups = (
            (self.bid_quotes, self.bid_quote_ages, -np.inf),
            (self.ask_quotes, self.ask_quote_ages, np.inf),
        )
        for quotes, ages, inactive_value in quote_groups:
            active = ages >= 0
            ages[active] += 1
            expired = ages >= self.config.quote_ttl_steps
            quotes[expired] = inactive_value
            ages[expired] = -1

    def _simulate_external_order_flow(self) -> None:
        """Inject passive fill opportunities so quoting can be learned."""
        if self.np_random.random() > self.config.external_order_flow_prob:
            return

        suit = int(self.np_random.integers(0, self.num_suits))
        if self.np_random.random() < 0.5:
            price, buyer = self._best_bid(suit)
            if buyer is not None:
                seller = self._random_counterparty(
                    side="sell", suit=suit, price=price, excluding_player=buyer
                )
                if seller is None:
                    return
                self._trade(
                    buyer, seller, suit, price,
                    by_quote_fill=buyer == self.agent_idx,
                    aggressor_side="sell",
                )
        else:
            price, seller = self._best_ask(suit)
            if seller is not None:
                buyer = self._random_counterparty(
                    side="buy", suit=suit, price=price, excluding_player=seller
                )
                if buyer is None:
                    return
                self._trade(
                    buyer, seller, suit, price,
                    by_quote_fill=seller == self.agent_idx,
                    aggressor_side="buy",
                )

    def _random_counterparty(
        self,
        *,
        side: str,
        suit: int,
        price: float,
        excluding_player: int,
    ) -> int | None:
        if side == "sell":
            candidates = np.flatnonzero(self.inventories[:, suit] > 0)
        else:
            candidates = np.flatnonzero(self.cash >= price)
        candidates = candidates[candidates != excluding_player]
        if candidates.size == 0:
            return None
        return int(candidates[int(self.np_random.integers(0, candidates.size))])

    def _trade(
        self,
        buyer_idx: int,
        seller_idx: int,
        suit: int,
        price: float,
        by_quote_fill: bool,
        aggressor_side: str,
    ) -> None:
        if seller_idx != -1 and self.inventories[seller_idx, suit] <= 0:
            return
        if buyer_idx != -1 and self.cash[buyer_idx] < price:
            return

        if seller_idx != -1:
            self.inventories[seller_idx, suit] -= 1
            self.cash[seller_idx] += price
        if buyer_idx != -1:
            self.inventories[buyer_idx, suit] += 1
            self.cash[buyer_idx] -= price

        reference = float(self._reference_prices()[suit])
        self.last_trade_price[suit] = price
        self.has_traded[suit] = True
        signed_volume = 1.0 if aggressor_side == "buy" else -1.0
        self.last_trade_signed_volume[suit] = signed_volume
        self.belief_flow *= self.config.belief_flow_decay
        self.belief_flow[suit] += signed_volume
        self.cumulative_signed_flow[suit] += signed_volume

        if buyer_idx == self.agent_idx or seller_idx == self.agent_idx:
            self.agent_trade_count += 1
            if by_quote_fill:
                self.agent_quote_fill_count += 1
            mid = reference
            if buyer_idx == self.agent_idx:
                self.agent_spread_capture += mid - price
            if seller_idx == self.agent_idx:
                self.agent_spread_capture += price - mid

    def _apply_semantic_action(self, player_idx: int, action: OpponentAction) -> None:
        kind = action.kind
        suit = action.suit

        if kind == "hold":
            return
        if suit is None:
            return
        if suit < 0 or suit >= self.num_suits:
            return

        if kind == "quote_bid":
            quote = self._resolve_quote_price(action)
            self.bid_quotes[player_idx, suit] = quote
            self.bid_quote_ages[player_idx, suit] = 0
            return

        if kind == "quote_ask":
            quote = self._resolve_quote_price(action)
            self.ask_quotes[player_idx, suit] = quote
            self.ask_quote_ages[player_idx, suit] = 0
            return

        if kind == "buy":
            price, seller = self._best_ask(suit, excluding_player=player_idx)
            buyer = player_idx
            if seller is None:
                if self.config.market_mode == "endogenous":
                    return
                if self.np_random.random() > self.config.external_fill_prob:
                    return
                seller = self._random_counterparty(
                    side="sell", suit=suit, price=price, excluding_player=buyer
                )
                if seller is None:
                    return
            self._trade(
                buyer, seller, suit, price,
                by_quote_fill=seller == self.agent_idx,
                aggressor_side="buy",
            )
            return

        if kind == "sell":
            price, buyer = self._best_bid(suit, excluding_player=player_idx)
            seller = player_idx
            if buyer is None:
                if self.config.market_mode == "endogenous":
                    return
                if self.np_random.random() > self.config.external_fill_prob:
                    return
                buyer = self._random_counterparty(
                    side="buy", suit=suit, price=price, excluding_player=seller
                )
                if buyer is None:
                    return
            self._trade(
                buyer, seller, suit, price,
                by_quote_fill=buyer == self.agent_idx,
                aggressor_side="sell",
            )
            return

    def _build_observation(self, player_idx: int) -> np.ndarray:
        own_bid_quote, own_ask_quote = self._player_quotes(player_idx)
        obs_bid, obs_ask, bid_available, ask_available, _, _ = self._book_arrays(player_idx)
        return build_policy_observation(
            inventory=self.inventories[player_idx],
            cash=float(self.cash[player_idx]),
            best_bid=obs_bid.astype(np.float32),
            best_ask=obs_ask.astype(np.float32),
            own_bid_quote=own_bid_quote,
            own_ask_quote=own_ask_quote,
            last_trade_price=self.last_trade_price,
            last_trade_signed_volume=self.last_trade_signed_volume,
            belief_flow=self.belief_flow,
            time_remaining=(self.config.max_steps - self.current_step) / self.config.max_steps,
            step_fraction=self.current_step / self.config.max_steps,
            include_belief_features=self.config.include_belief_features,
            initial_inventory=self.initial_inventories[player_idx],
            include_goal_belief_features=self.config.include_goal_belief_features,
            bid_available=bid_available if self.config.market_mode == "endogenous" else None,
            ask_available=ask_available if self.config.market_mode == "endogenous" else None,
        )

    def _opponent_view(self, opponent_idx: int) -> OpponentView:
        own_bid_quote, own_ask_quote = self._player_quotes(opponent_idx)
        _, _, bid_available, ask_available, view_bid, view_ask = self._book_arrays(opponent_idx)
        return OpponentView(
            inventory=self.inventories[opponent_idx].copy(),
            cash=float(self.cash[opponent_idx]),
            best_bid=view_bid.astype(np.float32),
            best_ask=view_ask.astype(np.float32),
            own_bid_quote=own_bid_quote.copy(),
            own_ask_quote=own_ask_quote.copy(),
            last_trade_price=self.last_trade_price.copy(),
            last_trade_signed_volume=self.last_trade_signed_volume.copy(),
            belief_flow=self.belief_flow.copy(),
            time_remaining=(self.config.max_steps - self.current_step) / self.config.max_steps,
            step=self.current_step,
            max_steps=self.config.max_steps,
            initial_inventory=self.initial_inventories[opponent_idx].copy(),
            cumulative_signed_flow=self.cumulative_signed_flow.copy(),
            market_mode=self.config.market_mode,
            bid_available=bid_available.copy(),
            ask_available=ask_available.copy(),
        )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if seed is not None:
            self.np_random = np.random.default_rng(seed)

        self._reset_state()
        # Rotate the learner and price-time tie priority so neither receives a
        # permanent advantage from seat order.
        self.agent_idx = int(self.np_random.integers(self.config.num_players))
        self.opponent_seats = [
            seat for seat in range(self.config.num_players) if seat != self.agent_idx
        ]
        self._tie_break_start = int(self.np_random.integers(self.config.num_players))
        self._action_order_start = int(self.np_random.integers(self.config.num_players))
        deal = deal_round(
            self.np_random,
            num_players=self.config.num_players,
            hand_size=10,
        )
        self.inventories = deal.inventories.copy()
        self.initial_inventories = deal.inventories.copy()
        self.goal_suit_idx = int(deal.goal_suit_idx)
        self.heavy_suit_idx = int(deal.heavy_suit_idx)
        self.suit_distribution = deal.suit_distribution.copy()

        obs = self._build_observation(self.agent_idx)
        info = {
            "agent_seat": self.agent_idx,
            "quote_tie_break_start": self._tie_break_start,
            "action_order_start": self._action_order_start,
            "goal_suit_idx": self.goal_suit_idx,
            "heavy_suit_idx": self.heavy_suit_idx,
            "suit_distribution": self.suit_distribution.copy(),
            "observation_spec": self.observation_spec,
            "market_mode": self.config.market_mode,
            "action_meanings": [
                self.describe_action(
                    action_idx, self.num_suits, market_mode=self.config.market_mode
                )
                for action_idx in range(self.action_space.n)
            ],
            "opponent_difficulties": self._opponent_difficulty_labels,
            "opponent_difficulty_by_player": (
                {
                    f"player_{seat}": lab
                    for seat, lab in zip(self.opponent_seats, self._opponent_difficulty_labels)
                }
                if self._opponent_difficulty_labels
                else None
            ),
            "opponent_difficulty_score": (
                float(sum(OPPONENT_DIFFICULTY_SCORE[d] for d in self._opponent_difficulty_labels))
                if self._opponent_difficulty_labels
                else None
            ),
        }
        return obs, info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self.current_step >= self.config.max_steps:
            raise RuntimeError("Episode already ended. Call reset() before step().")
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action {action}")

        before_value = self._mark_to_market(self.agent_idx)
        self._age_and_expire_quotes()

        for offset in range(self.config.num_players):
            player_idx = (self._action_order_start + offset) % self.config.num_players
            if player_idx == self.agent_idx:
                self._apply_semantic_action(player_idx, self._decode_agent_action(action))
                continue
            policy_idx = self.opponent_seats.index(player_idx)
            policy = self.opponent_policies[policy_idx]
            view = self._opponent_view(player_idx)
            self._apply_semantic_action(
                player_idx, policy.act(view=view, rng=self.np_random)
            )

        if self.config.market_mode == "exogenous":
            self._simulate_external_order_flow()
        post_trade_value = self._mark_to_market(self.agent_idx)
        if self.config.market_mode == "exogenous":
            self._update_external_book()
        after_value = self._mark_to_market(self.agent_idx)
        trade_reward = post_trade_value - before_value
        inventory_reward = after_value - post_trade_value
        reward = trade_reward + inventory_reward

        self.current_step += 1
        terminated = self.current_step >= self.config.max_steps
        truncated = False

        info: dict[str, Any] = {
            "mark_to_market": after_value,
            "agent_inventory_abs": float(np.sum(np.abs(self.inventories[self.agent_idx]))),
            "agent_trade_count": self.agent_trade_count,
            "reward_breakdown": {
                "trade_reward": float(trade_reward),
                "inventory_reward": float(inventory_reward),
                "settlement_reward": 0.0,
            },
        }

        if terminated:
            terminal_inventories = self.inventories.copy()
            settled = settle_round(
                inventories=self.inventories,
                cash=self.cash,
                goal_suit_idx=self.goal_suit_idx,
                goal_card_value=self.config.goal_card_value,
                goal_majority_bonus=self.config.goal_majority_bonus,
                total_pot=(
                    self.config.ante * self.config.num_players
                    if self.config.pot_conserving_settlement
                    else None
                ),
            )
            self.cash = settled
            terminal_delta = float(self.cash[self.agent_idx] - after_value)
            reward += terminal_delta
            info["reward_breakdown"]["settlement_reward"] = terminal_delta

            fill_rate = (
                self.agent_quote_fill_count / self.agent_trade_count
                if self.agent_trade_count > 0
                else 0.0
            )
            info.update(
                {
                    "terminal_settlement_delta": terminal_delta,
                    "final_bankroll": float(self.cash[self.agent_idx]),
                    "final_bankrolls": self.cash.copy(),
                    "final_rank": int(
                        1 + np.sum(self.cash > self.cash[self.agent_idx])
                    ),
                    "winner_indices": np.flatnonzero(
                        self.cash == np.max(self.cash)
                    ).tolist(),
                    "goal_suit_idx": self.goal_suit_idx,
                    "agent_quote_fill_rate": float(fill_rate),
                    "market_mode": self.config.market_mode,
                    "action_meanings": [
                        self.describe_action(
                            action_idx, self.num_suits, market_mode=self.config.market_mode
                        )
                        for action_idx in range(self.action_space.n)
                    ],
                    "agent_avg_spread_capture": float(
                        self.agent_spread_capture / max(self.agent_trade_count, 1)
                    ),
                    "opponent_difficulties": self._opponent_difficulty_labels,
                    "opponent_difficulty_by_player": (
                        {
                            f"player_{seat}": lab
                            for seat, lab in zip(self.opponent_seats, self._opponent_difficulty_labels)
                        }
                        if self._opponent_difficulty_labels
                        else None
                    ),
                    "opponent_difficulty_score": (
                        float(sum(OPPONENT_DIFFICULTY_SCORE[d] for d in self._opponent_difficulty_labels))
                        if self._opponent_difficulty_labels
                        else None
                    ),
                    "episode_metrics": {
                        "final_bankroll": float(self.cash[self.agent_idx]),
                        "inventory_risk": float(np.sum(np.abs(terminal_inventories[self.agent_idx]))),
                        "quote_fill_rate": float(fill_rate),
                        "avg_spread_capture": float(
                            self.agent_spread_capture / max(self.agent_trade_count, 1)
                        ),
                    },
                }
            )
            self.inventories[:] = 0

        obs = self._build_observation(self.agent_idx)
        return obs, float(reward), terminated, truncated, info
