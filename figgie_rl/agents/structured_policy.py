"""Conditional kind/suit/price probabilities over the existing 105 actions."""

from __future__ import annotations
import math
import torch
from torch import nn
from sb3_contrib.common.maskable.policies import MaskableActorCriticPolicy
from figgie_rl.envs.simple_figgie_env import SimpleFiggieEnv

KINDS = ("hold", "quote_bid", "quote_ask", "buy", "sell")


class StructuredActionHead(nn.Module):
    """P(kind) P(suit|kind) P(price|kind,suit), with price only for quotes.

    The joint logits retain the exact existing action table. MaskablePPO then
    excludes infeasible leaves and renormalizes the joint distribution. There
    are no duplicate hold/trade representations and no independent invalid
    MultiDiscrete tuples. Masking is deliberately separate from factorization.
    """

    def __init__(self, latent_dim: int):
        super().__init__()
        self.kind = nn.Linear(latent_dim, 5)
        self.suit = nn.Linear(latent_dim, 4 * 4)
        self.price = nn.Linear(latent_dim, 2 * 4 * 12)
        table = SimpleFiggieEnv.build_action_table(4, "endogenous")
        self.register_buffer(
            "kind_index", torch.tensor([KINDS.index(k) for k, _, _ in table])
        )
        self.register_buffer(
            "suit_index", torch.tensor([0 if s is None else s for _, s, _ in table])
        )
        self.register_buffer(
            "price_index", torch.tensor([0 if p is None else p for _, _, p in table])
        )
        for layer in (self.kind, self.suit, self.price):
            nn.init.orthogonal_(layer.weight, gain=0.01)
            nn.init.zeros_(layer.bias)
        # Equalize initial probability across the 105 leaves, rather than
        # assigning 1/5 to hold and to each whole quote branch.
        with torch.no_grad():
            self.kind.bias.copy_(torch.tensor([math.log(n) for n in (1, 48, 48, 4, 4)]))

    def forward(self, latent):
        kind = torch.log_softmax(self.kind(latent), dim=-1)
        suit = torch.log_softmax(self.suit(latent).reshape(-1, 4, 4), dim=-1)
        price = torch.log_softmax(self.price(latent).reshape(-1, 2, 4, 12), dim=-1)
        k, s, p = self.kind_index, self.suit_index, self.price_index
        result = kind[:, k]
        result = result + suit[:, (k - 1).clamp(min=0), s] * (k != 0)
        result = result + price[:, (k - 1).clamp(min=0, max=1), s, p] * (
            (k == 1) | (k == 2)
        )
        return result


class StructuredMaskablePolicy(MaskableActorCriticPolicy):
    def _build(self, lr_schedule):
        super()._build(lr_schedule)
        if self.action_space.n != 105:
            raise ValueError(
                "Structured policy requires the four-suit endogenous 105-action schema"
            )
        self.action_net = StructuredActionHead(self.mlp_extractor.latent_dim_pi)
        self.optimizer = self.optimizer_class(
            self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs
        )
