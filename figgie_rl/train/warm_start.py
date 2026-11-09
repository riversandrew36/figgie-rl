"""Warm-start a masked PPO actor and critic from scripted teacher play."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch.nn import functional as F

from figgie_rl.agents.baselines import policy_for_difficulty
from figgie_rl.envs.action_interface import legal_action_mask
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv


@dataclass(frozen=True)
class Demonstrations:
    observations: np.ndarray
    actions: np.ndarray
    masks: np.ndarray
    returns: np.ndarray
    dropped_infeasible: int
    mean_profit: float


def collect_demonstrations(
    env_config: EnvConfig, teacher: str, first_seed: int, episodes: int
) -> Demonstrations:
    """Play a teacher in the learner seat, recording only what the learner can see.

    Returns are undiscounted reward-to-go in the environment's reward scale.
    Teacher actions that the mask forbids are dropped from the training samples
    but still played, so the recorded returns describe the teacher's real rounds.
    """
    env = SimpleFiggieEnv(env_config)
    policy = policy_for_difficulty(teacher)
    observations, actions, masks, returns = [], [], [], []
    dropped = 0
    profits = []
    for episode in range(episodes):
        seed = first_seed + episode
        obs, _ = env.reset(seed=seed)
        rng = np.random.default_rng(seed + 900_000)
        rewards: list[float] = []
        keep: list[bool] = []
        done = False
        info: dict = {}
        while not done:
            mask = legal_action_mask(env)
            action = env.encode_semantic_action(
                policy.act(env._opponent_view(env.agent_idx), rng)
            )
            feasible = bool(mask[action])
            dropped += int(not feasible)
            keep.append(feasible)
            if feasible:
                observations.append(obs.copy())
                actions.append(action)
                masks.append(mask)
            obs, reward, terminated, truncated, info = env.step(action)
            rewards.append(float(reward))
            done = terminated or truncated
        to_go = np.cumsum(rewards[::-1])[::-1]
        returns.extend(float(value) for value, kept in zip(to_go, keep) if kept)
        profits.append(float(info["final_bankroll"]) - env.config.starting_cash)
    env.close()
    return Demonstrations(
        observations=np.asarray(observations, dtype=np.float32),
        actions=np.asarray(actions, dtype=np.int64),
        masks=np.asarray(masks, dtype=bool),
        returns=np.asarray(returns, dtype=np.float32),
        dropped_infeasible=dropped,
        mean_profit=float(np.mean(profits)),
    )


def imitation_agreement(model, data: Demonstrations) -> float:
    """Fraction of states where the masked greedy action equals the teacher's."""
    device = model.device
    with torch.no_grad():
        chosen = model.policy.get_distribution(
            torch.as_tensor(data.observations, device=device),
            action_masks=torch.as_tensor(data.masks, device=device),
        ).mode()
    return float((chosen.cpu().numpy() == data.actions).mean())


def pretrain(
    model,
    data: Demonstrations,
    *,
    epochs: int,
    batch_size: int = 1024,
    learning_rate: float = 1e-3,
    seed: int = 0,
) -> dict[str, float]:
    """Fit the actor to teacher actions and the critic to teacher returns.

    The critic matters as much as the actor: PPO advantages from an untrained
    critic can erase an imitated policy during its first updates. A separate
    optimizer leaves PPO's own optimizer state untouched.
    """
    policy = model.policy
    device = model.device
    observations = torch.as_tensor(data.observations, device=device)
    actions = torch.as_tensor(data.actions, device=device)
    masks = torch.as_tensor(data.masks, device=device)
    returns = torch.as_tensor(data.returns, device=device)
    optimizer = torch.optim.Adam(policy.parameters(), lr=learning_rate)
    rng = np.random.default_rng(seed)
    actor_loss = critic_loss = float("nan")
    for _ in range(epochs):
        order = rng.permutation(len(actions))
        actor_total = critic_total = 0.0
        batches = 0
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            values, log_prob, _ = policy.evaluate_actions(
                observations[batch], actions[batch], action_masks=masks[batch]
            )
            actor = -log_prob.mean()
            critic = F.mse_loss(values.flatten(), returns[batch])
            optimizer.zero_grad()
            (actor + critic).backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optimizer.step()
            actor_total += float(actor.detach())
            critic_total += float(critic.detach())
            batches += 1
        actor_loss = actor_total / batches
        critic_loss = critic_total / batches
    return {"actor_loss": actor_loss, "critic_loss": critic_loss}
