"""Teacher warm start uses visible state and improves imitation."""

import numpy as np
from sb3_contrib import MaskablePPO
from stable_baselines3.common.vec_env import DummyVecEnv

from figgie_rl.envs.action_interface import ActionInterface
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.train.warm_start import (
    collect_demonstrations,
    imitation_agreement,
    pretrain,
)

CONFIG = EnvConfig(
    market_mode="endogenous",
    max_steps=40,
    reward_scale=0.02,
    gamma=1.0,
    include_belief_features=True,
    include_goal_belief_features=True,
    include_player_history_features=True,
    opponent_difficulties=("hunter", "banker", "detective"),
)


def test_demonstrations_are_aligned_masked_and_scaled():
    data = collect_demonstrations(CONFIG, "hunter", 100, 5)
    count = len(data.actions)
    assert count + data.dropped_infeasible == 5 * 40
    assert data.observations.shape == (count, 71)
    assert data.masks.shape == (count, 105)
    assert data.returns.shape == (count,)
    assert data.masks[np.arange(count), data.actions].all()
    assert np.abs(data.returns).max() < 10.0


def test_pretraining_improves_agreement_and_fits_returns():
    data = collect_demonstrations(CONFIG, "hunter", 100, 20)
    env = DummyVecEnv([lambda: ActionInterface(SimpleFiggieEnv(CONFIG))])
    model = MaskablePPO("MlpPolicy", env, n_steps=64, batch_size=32, seed=1, device="cpu")
    before = imitation_agreement(model, data)
    losses = pretrain(model, data, epochs=20, batch_size=128, seed=1)
    assert imitation_agreement(model, data) > max(before, 0.5)
    assert losses["critic_loss"] < float(np.var(data.returns))
