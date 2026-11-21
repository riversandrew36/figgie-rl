"""Regenerate the browser actors and their fixed-deal Python parity fixtures."""

import argparse
import json
from pathlib import Path
from statistics import median

from sb3_contrib import MaskablePPO
import torch
from torch import nn
import yaml

from figgie_rl.agents.baselines import OpponentAction
from figgie_rl.envs.action_interface import ActionInterface
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from scripts.export_rl_showcase import ARENA, CONFIG, RESULTS, ROOT, build_showcase
from scripts.export_rule_fixtures import Hold

POLICY_IDS = ("ppo_goal_shown", "ppo_no_aids")


def load_actor(step: dict, seed: int, definition: dict) -> tuple:
    model = MaskablePPO.load(
        RESULTS / f"step_{step['number']}_{step['name']}/seed_{seed}.zip", device="cpu",
    )
    env = SimpleFiggieEnv(EnvConfig(
        **definition["env"], include_goal_oracle_features=True,
        include_goal_belief_features=True, hidden_observation_blocks=tuple(step.get("hide", [])),
    ), opponent_policies=[Hold(), Hold(), Hold()])
    layers = []
    for layer in [*model.policy.mlp_extractor.policy_net, model.policy.action_net]:
        if isinstance(layer, nn.Linear):
            layers.append({
                "type": "linear",
                "weights": [[round(value, 9) for value in row] for row in layer.weight.detach().float().tolist()],
                "bias": [round(value, 9) for value in layer.bias.detach().float().tolist()],
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
    return model, ActionInterface(env), {
        "algorithm": "MaskablePPO", "seed": seed, "layers": layers, "actions": actions,
        "normalization": None, "observation_spec": env.observation_spec,
        "hidden_blocks": list(env.config.hidden_observation_blocks),
    }


def probe(model, wrapper, deal: int) -> dict:
    env = wrapper.unwrapped
    wrapper.reset(seed=5400000 + deal)
    env.agent_idx = 0
    order = deal % 4
    tie = (deal + 1) % 4
    env._action_order_start = order
    env._tie_break_start = tie
    inventories = env.inventories.tolist()
    first = next(suit for suit, count in enumerate(inventories[1]) if count)
    second = next(suit for suit, count in enumerate(inventories[2]) if count)
    # A resting offer expires, followed by two crossings (one on each side).
    script = {
        0: {1: {"kind": "quote_ask", "suit": first, "price": 8}},
        10: {0: {"kind": "quote_bid", "suit": first, "price": 10}},
        11: {1: {"kind": "quote_ask", "suit": first, "price": 6}},
        12: {2: {"kind": "quote_ask", "suit": second, "price": 8}},
        13: {0: {"kind": "quote_bid", "suit": second, "price": 12}},
        118: {0: {"kind": "quote_bid", "suit": first, "price": 4}},
        119: {1: {"kind": "sell", "suit": first}},
    }
    decisions = []
    for tick in range(env.config.max_steps):
        env.current_step = tick
        # Keep the quote-aging and trade windows, plus late-round observations.
        if tick <= 14 and tick != 2 or tick >= 118:
            obs = env._build_observation(0)
            mask = wrapper.action_masks()
            with torch.inference_mode():
                features = model.policy.extract_features(torch.from_numpy(obs).unsqueeze(0))
                logits = model.policy.action_net(model.policy.mlp_extractor.forward_actor(features))
            raw = logits.squeeze(0).tolist()
            decisions.append({
                "tick": tick, "observation": obs.tolist(), "mask": mask.tolist(),
                "logits": [round(value, 6) for value in raw],
                "argmax": max((i for i, valid in enumerate(mask) if valid), key=raw.__getitem__),
            })
        # Same action pipeline as SimpleFiggieEnv.step, with fixed actions for
        # every seat in place of learned and scripted bot decisions.
        env._age_and_expire_quotes()
        for offset in range(4):
            seat = (order + offset) % 4
            action = script.get(tick, {}).get(seat)
            if action:
                env._apply_semantic_action(seat, OpponentAction(
                    action["kind"], suit=action["suit"], limit_price=action.get("price"),
                ))
    return {
        "inventories": inventories, "goalSuitIdx": env.goal_suit_idx, "order": order,
        "tie": tie, "actions": script, "decisions": decisions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, default=ARENA / "policies")
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/browser/fixtures/ppo_lab_parity.json")
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    study = build_showcase()
    final = study["steps"][2]
    seed = next(line["seed"] for line, profit in zip(final["series"], final["final"], strict=True)
                if profit == median(final["final"]))
    definition = yaml.safe_load(CONFIG.read_text())
    fixtures = {}
    for name, index in zip(POLICY_IDS, (0, 2), strict=True):
        model, env, payload = load_actor(definition["steps"][index], seed, definition)
        data = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        path = args.destination / f"{name}.js"
        path.write_text(f'globalThis.figgiePolicies ??= {{}};\nglobalThis.figgiePolicies.{name} = {data};\n')
        if path.stat().st_size > 400_000:
            raise ValueError(f"Policy exceeds browser budget: {path}")
        fixtures[name] = [probe(model, env, deal) for deal in range(6)]
        print(f"{path.name}: {path.stat().st_size:,} bytes")
    # Shared fields are identical for both policies except observation hints
    # and policy outputs. Pack the Boolean masks to keep the fixture small.
    paired = {}
    for name, deals in fixtures.items():
        for deal in deals:
            for decision in deal["decisions"]:
                decision["mask"] = "".join("1" if valid else "0" for valid in decision["mask"])
                decision["observation"] = [round(value, 8) for value in decision["observation"]]
        paired[name] = deals
    args.fixture.write_text(json.dumps(paired, separators=(",", ":"), allow_nan=False) + "\n")
    print(f"{args.fixture.name}: {args.fixture.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
