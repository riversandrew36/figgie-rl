"""Scripted baseline opponents and playing styles."""

from figgie_rl.agents.baselines import (
    OPPONENT_DIFFICULTY_CHOICES,
    OPPONENT_DIFFICULTY_SCORE,
    PLAYING_STYLES,
    BaselinePolicy,
    BayesianGoalTrader,
    InventoryAwareMarketMaker,
    NaiveGoalBuyer,
    RandomTrader,
    ReservationMarketMaker,
    RuleBasedValueTrader,
    policies_from_difficulties,
    policy_for_difficulty,
)
from figgie_rl.agents.styles import Bluffer, GoalHunter, SpreadBanker, TapeDetective

__all__ = [
    "OPPONENT_DIFFICULTY_CHOICES",
    "OPPONENT_DIFFICULTY_SCORE",
    "PLAYING_STYLES",
    "BaselinePolicy",
    "BayesianGoalTrader",
    "NaiveGoalBuyer",
    "ReservationMarketMaker",
    "GoalHunter",
    "SpreadBanker",
    "TapeDetective",
    "Bluffer",
    "RandomTrader",
    "InventoryAwareMarketMaker",
    "RuleBasedValueTrader",
    "policies_from_difficulties",
    "policy_for_difficulty",
]
