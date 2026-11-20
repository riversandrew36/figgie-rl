"""Export local policy diagnostics and a fixed-deal observation parity probe.

Network exports are diagnostic only. They are never staged into the arena.
"""

import argparse
import json
from pathlib import Path
from statistics import median

import numpy as np
from sb3_contrib import MaskablePPO
import torch
from torch import nn
import yaml

from figgie_rl.agents.baselines import OpponentAction
from figgie_rl.envs.action_interface import ActionInterface
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from scripts.export_rl_showcase import CONFIG, RESULTS, build_showcase
from scripts.export_rule_fixtures import DEAL_8, Hold


def export_checkpoint(step: dict, seed: int, destination: Path) -> None:
    definition = yaml.safe_load(CONFIG.read_text())
    model = MaskablePPO.load(
        RESULTS / f"step_{step['number']}_{step['name']}/seed_{seed}.zip",
        device="cpu",
    )
    env = SimpleFiggieEnv(EnvConfig(
        **definition["env"],
        include_goal_oracle_features=True,
        include_goal_belief_features=True,
        hidden_observation_blocks=tuple(step.get("hide", [])),
    ), opponent_policies=[Hold(), Hold(), Hold()])
    wrapper = ActionInterface(env)
    wrapper.reset(seed=seed)
    env.agent_idx = 0
    env.inventories[:] = env.initial_inventories[:] = np.array(DEAL_8)
    env.goal_suit_idx = 0
    layers = []
    for layer in [*model.policy.mlp_extractor.policy_net, model.policy.action_net]:
        if isinstance(layer, nn.Linear):
            layers.append({
                "type": "linear",
                "shape": list(layer.weight.shape),
                "weights": layer.weight.detach().float().tolist(),
                "bias": layer.bias.detach().float().tolist(),
            })
        elif isinstance(layer, (nn.Tanh, nn.ReLU)):
            layers.append({"type": type(layer).__name__.lower()})
        else:
            raise ValueError(f"Unsupported actor layer: {layer}")
    if model.get_vec_normalize_env() is not None:
        raise ValueError("Checkpoint requires a VecNormalize state export")
    actions = []
    for index in range(env.action_space.n):
        action = env.decode_discrete_action(index, env.num_suits, env.config.market_mode)
        actions.append({"kind": action.kind, "suit": action.suit, "price": action.limit_price})
    payload = {
        "algorithm": "MaskablePPO", "seed": seed, "layers": layers, "actions": actions,
        "normalization": None, "observation_spec": env.observation_spec,
        "hidden_blocks": list(env.config.hidden_observation_blocks), "requires_action_mask": True,
    }
    path = destination / f"step-{step['number']}-policy.json"
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    if path.stat().st_size >= 600_000:
        raise ValueError(f"Policy exceeds browser budget: {path}")
    env._apply_semantic_action(1, OpponentAction("quote_ask", suit=0, limit_price=8))
    probe = []
    for decision in range(9):
        env.current_step = decision
        obs = env._build_observation(0)
        mask = wrapper.action_masks()
        with torch.inference_mode():
            features = model.policy.extract_features(torch.from_numpy(obs).unsqueeze(0))
            logits = model.policy.action_net(model.policy.mlp_extractor.forward_actor(features))
        values = logits.squeeze(0).tolist()
        probe.append({
            "decision": decision, "browser_tick": 2 * decision, "observation": obs.tolist(),
            "logits": values, "mask": mask.tolist(),
            "argmax": max((i for i, valid in enumerate(mask) if valid), key=values.__getitem__),
            "best_ask": float(env._best_ask(0, excluding_player=0)[0]) if decision < 8 else None,
        })
        env._age_and_expire_quotes()
    (destination / f"step-{step['number']}-quote-probe.json").write_text(
        json.dumps({"inventories": DEAL_8, "goalSuitIdx": 0, "steps": probe}, separators=(",", ":")) + "\n"
    )
    print(f"{path.name}: {path.stat().st_size:,} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    destination = parser.parse_args().destination
    destination.mkdir(parents=True, exist_ok=True)
    study = build_showcase()
    final = study["steps"][2]
    seed = next(line["seed"] for line, profit in zip(final["series"], final["final"], strict=True)
                if profit == median(final["final"]))
    steps = yaml.safe_load(CONFIG.read_text())["steps"]
    for index in (0, 2):
        export_checkpoint(steps[index], seed, destination)


if __name__ == "__main__":
    main()
