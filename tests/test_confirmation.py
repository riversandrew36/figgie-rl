"""The matched trainer preserves equal staging and identical first-stage controls."""
import importlib.util
from copy import deepcopy
from pathlib import Path

import torch
from stable_baselines3 import PPO

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_confirmation.py"
spec = importlib.util.spec_from_file_location("confirmation", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_fixed_and_pool_have_matched_first_stage_and_step_budget(tmp_path, monkeypatch):
    settings = deepcopy(module.SPEC)
    settings.update(training_timesteps=16, self_play_iterations=2,
                    self_play_chunk_timesteps=8, historical_checkpoints=[])
    settings["env"]["max_steps"] = 2
    settings["train"].update(n_envs=1, n_steps=8, batch_size=8)
    monkeypatch.setattr(module, "SPEC", settings)
    monkeypatch.setattr(module, "OUT", tmp_path)
    monkeypatch.setattr(module, "artifact", lambda arm, seed: tmp_path / arm)
    for arm in ("fixed", "self_play"):
        module.train(arm, 101)
        record = module.load(tmp_path / "completed" / f"{arm}_seed_101.json")
        assert record["timesteps"] == 16
        assert (tmp_path / arm / "self_play/checkpoints/iter_001.metadata.json").exists()
    fixed = PPO.load(tmp_path / "fixed/self_play/checkpoints/iter_000.zip")
    pooled = PPO.load(tmp_path / "self_play/self_play/checkpoints/iter_000.zip")
    for key, value in fixed.policy.state_dict().items():
        assert torch.equal(value, pooled.policy.state_dict()[key]), key
