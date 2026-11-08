"""Observable feasibility masks; the underlying execution rules are unchanged."""

from __future__ import annotations
import gymnasium as gym
import numpy as np
from figgie_rl.agents.baselines import OpponentAction
from figgie_rl.envs.simple_figgie_env import ENDOGENOUS_PRICE_LADDER, SimpleFiggieEnv

# The 33/105 leaf descriptions are immutable action schemas; build once.
_ACTION_TABLES = {
    mode: tuple(SimpleFiggieEnv.build_action_table(4, mode))
    for mode in ("exogenous", "endogenous")
}


def legal_action_mask(env: SimpleFiggieEnv) -> np.ndarray:
    """Use own holdings/cash and public best quotes, never opponent holdings.

    These are decision-time feasibility checks. Earlier actors can change the
    book before execution. Quote masks require current cash/card backing per
    quote; they do not reserve resources across quotes or guarantee a fill.
    """
    player = env.agent_idx
    cash = float(env.cash[player])
    inventory = env.inventories[player]
    _, _, bid_available, ask_available, public_bid, public_ask = env._book_arrays(
        player
    )
    table = _ACTION_TABLES[env.config.market_mode]
    mask = np.ones(env.action_space.n, dtype=bool)
    for index, (kind, suit, level) in enumerate(table[1:], start=1):
        suit = int(suit)
        if kind == "quote_bid":
            limit_price = (
                float(ENDOGENOUS_PRICE_LADDER[int(level)])
                if env.config.market_mode == "endogenous"
                else None
            )
            action = OpponentAction(
                kind, suit=suit, price_level=int(level), limit_price=limit_price
            )
            mask[index] = cash >= env._resolve_quote_price(action)
        elif kind == "quote_ask":
            mask[index] = inventory[suit] > 0
        elif kind == "buy":
            mask[index] = bool(ask_available[suit]) and cash >= public_ask[suit]
        elif kind == "sell":
            mask[index] = bool(bid_available[suit]) and inventory[suit] > 0
    return mask


class ActionInterface(gym.Wrapper):
    """Expose masks to MaskablePPO without remapping legacy action indices."""

    def action_masks(self) -> np.ndarray:
        return legal_action_mask(self.env.unwrapped)
