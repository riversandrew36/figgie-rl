"""Educational utility for inspecting the Figgie environment by hand."""

from __future__ import annotations

import argparse

import numpy as np

from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a simplified Figgie environment episode.")
    parser.add_argument("--seed", type=int, default=7, help="Environment seed.")
    parser.add_argument("--steps", type=int, default=5, help="How many random steps to print.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = SimpleFiggieEnv(config=EnvConfig(seed=args.seed))
    obs, info = env.reset(seed=args.seed)

    print("=== Simplified Figgie Demo ===")
    print(f"Observation shape: {obs.shape}")
    print("Observation spec:")
    for key, width in info["observation_spec"].items():
        print(f"  - {key}: {width}")

    print("\nAction meanings:")
    for idx, description in enumerate(info["action_meanings"]):
        print(f"  {idx:02d}: {description}")

    print("\nOpponent curriculum (scripted seats vs learning agent at player 0):")
    print(f"  opponent_difficulties={info.get('opponent_difficulties')}")
    print(f"  opponent_difficulty_by_player={info.get('opponent_difficulty_by_player')}")
    print(f"  opponent_difficulty_score={info.get('opponent_difficulty_score')}")

    print("\nInitial hidden round metadata (normally not given to the agent):")
    print(f"  heavy_suit_idx={info['heavy_suit_idx']}, goal_suit_idx={info['goal_suit_idx']}")
    print(f"  suit_distribution={info['suit_distribution'].tolist()}")

    print("\nSample random rollout:")
    rng = np.random.default_rng(args.seed)
    for step_idx in range(args.steps):
        action = int(rng.integers(0, env.action_space.n))
        obs, reward, terminated, truncated, step_info = env.step(action)
        print(
            f"  step={step_idx:02d} action={action:02d} "
            f"({env.describe_action(action, env.num_suits)}) reward={reward:.3f} "
            f"breakdown={step_info['reward_breakdown']}"
        )
        if terminated or truncated:
            print("  episode ended early")
            break

    env.close()


if __name__ == "__main__":
    main()
