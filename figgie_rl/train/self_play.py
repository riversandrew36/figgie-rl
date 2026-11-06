"""Staged self-play training for improved Figgie policies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from figgie_rl.agents.baselines import (
    BaselinePolicy,
    BayesianGoalTrader,
    InventoryAwareMarketMaker,
    OpponentAction,
    OpponentView,
    RandomTrader,
    ReservationMarketMaker,
    policies_from_difficulties,
)
from figgie_rl.envs.simple_figgie_env import (
    EnvConfig,
    MARKET_MODES,
    MISSING_VIEW_ASK,
    SimpleFiggieEnv,
    build_policy_observation,
)
from figgie_rl.envs.mechanics import SUITS
from figgie_rl.train.metadata import (
    build_training_metadata,
    metadata_path_for,
    write_model_metadata,
)


class FrozenPPOOpponent:
    """Adapter that lets a frozen PPO model act as scripted opponent."""

    def __init__(
        self, model_path: str, num_suits: int, env_config: EnvConfig | None = None
    ) -> None:
        self.model = PPO.load(model_path)
        self.num_suits = num_suits
        stem = Path(model_path)
        if stem.suffix == ".zip":
            stem = stem.with_suffix("")
        sidecar = metadata_path_for(stem)
        if sidecar.is_file():
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            saved_config = EnvConfig(**metadata["resolved_config"]["env"])
            if env_config is not None and any(
                getattr(saved_config, field) != getattr(env_config, field)
                for field in (
                    "market_mode", "include_belief_features", "include_goal_belief_features"
                )
            ):
                raise ValueError("Frozen PPO checkpoint schema does not match the self-play environment")
            env_config = saved_config
        if env_config is None:
            # Historical checkpoints have no metadata. Action count identifies
            # the market even when observation lengths overlap (notably 39).
            modes = [
                mode for mode in MARKET_MODES
                if self.model.action_space.n == len(
                    SimpleFiggieEnv.build_action_table(num_suits, market_mode=mode)
                )
            ]
            if len(modes) != 1:
                raise ValueError("Unsupported frozen PPO action space")
            mode = modes[0]
            base_dim = num_suits * 7 + 3 + (2 * num_suits if mode == "endogenous" else 0)
            extra_dim = self.model.observation_space.shape[0] - base_dim
            if extra_dim not in (0, num_suits, 2 * num_suits):
                raise ValueError("Unsupported frozen PPO observation layout")
            # A single optional group historically meant flow. Pass env_config
            # for a goal-only checkpoint without a sidecar.
            env_config = EnvConfig(
                market_mode=mode,
                include_belief_features=extra_dim >= num_suits,
                include_goal_belief_features=extra_dim == 2 * num_suits,
            )
        self.config = env_config
        self.include_belief_features = env_config.include_belief_features
        self.include_goal_belief_features = env_config.include_goal_belief_features
        expected_dim = (
            num_suits * 7 + 3
            + num_suits * int(self.include_belief_features)
            + num_suits * int(self.include_goal_belief_features)
            + (2 * num_suits if env_config.market_mode == "endogenous" else 0)
        )
        expected_actions = len(SimpleFiggieEnv.build_action_table(
            num_suits, market_mode=env_config.market_mode
        ))
        if self.model.observation_space.shape != (expected_dim,) or self.model.action_space.n != expected_actions:
            raise ValueError("Frozen PPO observation/action spaces do not match its environment schema")

    def _obs_from_view(self, view: OpponentView) -> np.ndarray:
        if view.market_mode != self.config.market_mode:
            raise ValueError("Frozen PPO market mode does not match the opponent view")
        bid_available = ask_available = None
        best_bid, best_ask = view.best_bid, view.best_ask
        if self.config.market_mode == "endogenous":
            bid_available = (
                view.bid_available if view.bid_available is not None else view.best_bid > 0.0
            )
            ask_available = (
                view.ask_available if view.ask_available is not None
                else np.isfinite(view.best_ask) & (view.best_ask < MISSING_VIEW_ASK)
            )
            best_bid = np.where(bid_available, view.best_bid, 0.0)
            best_ask = np.where(ask_available, view.best_ask, 0.0)
        obs = build_policy_observation(
            inventory=view.inventory,
            cash=view.cash,
            best_bid=best_bid,
            best_ask=best_ask,
            own_bid_quote=view.own_bid_quote,
            own_ask_quote=view.own_ask_quote,
            last_trade_price=view.last_trade_price,
            last_trade_signed_volume=view.last_trade_signed_volume,
            belief_flow=view.belief_flow,
            time_remaining=view.time_remaining,
            step_fraction=view.step / max(view.max_steps, 1),
            include_belief_features=self.include_belief_features,
            initial_inventory=view.initial_inventory,
            include_goal_belief_features=self.include_goal_belief_features,
            bid_available=bid_available,
            ask_available=ask_available,
        )
        if obs.shape != self.model.observation_space.shape:
            raise ValueError(
                f"Frozen PPO observation shape {obs.shape} does not match "
                f"model shape {self.model.observation_space.shape}"
            )
        return obs

    def act(self, view: OpponentView, rng: np.random.Generator) -> OpponentAction:
        obs = self._obs_from_view(view)
        action, _ = self.model.predict(obs, deterministic=True)
        return SimpleFiggieEnv.decode_discrete_action(
            int(action), self.num_suits, market_mode=self.config.market_mode
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Self-play loop for Figgie RL.")
    parser.add_argument("--config", type=str, default="configs/ppo_self_play.yaml")
    parser.add_argument("--iterations", type=int, default=6)
    parser.add_argument("--chunk-timesteps", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=17)
    return parser.parse_args()


def load_yaml(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _choose_pool(
    checkpoint_paths: list[str],
    rng: np.random.Generator,
    num_suits: int,
    env_config: EnvConfig | None = None,
) -> list[BaselinePolicy]:
    if env_config is not None and env_config.opponent_difficulties is not None:
        pool = policies_from_difficulties(env_config.opponent_difficulties)
    elif env_config is not None and env_config.market_mode == "endogenous":
        pool = [ReservationMarketMaker(), ReservationMarketMaker(), BayesianGoalTrader()]
    else:
        pool = [RandomTrader(), InventoryAwareMarketMaker(), BayesianGoalTrader()]
    if checkpoint_paths:
        path = checkpoint_paths[int(rng.integers(0, len(checkpoint_paths)))]
        pool[-1] = FrozenPPOOpponent(path, num_suits=num_suits, env_config=env_config)
    return pool


def _make_env(env_cfg: dict[str, Any], seed: int, opponents: list[BaselinePolicy]) -> Monitor:
    merged_cfg = dict(env_cfg)
    merged_cfg.setdefault("include_belief_features", True)
    merged_cfg["seed"] = seed
    config = EnvConfig(**merged_cfg)
    env = SimpleFiggieEnv(config=config, opponent_policies=opponents)
    return Monitor(env)


def main() -> None:
    args = parse_args()
    if args.iterations <= 0:
        raise ValueError("--iterations must be > 0")
    if args.chunk_timesteps <= 0:
        raise ValueError("--chunk-timesteps must be > 0")

    cfg = load_yaml(args.config)
    env_cfg = dict(cfg["env"])
    env_cfg.setdefault("include_belief_features", True)
    cfg["env"] = env_cfg
    cfg["seed"] = args.seed
    env_config = EnvConfig(**env_cfg)
    train_cfg = cfg["train"]
    run_name = cfg.get("run_name", "ppo_simple")
    root_artifacts = Path(cfg.get("paths", {}).get("root_artifacts", "artifacts"))

    self_play_dir = root_artifacts / run_name / "self_play"
    ckpt_dir = self_play_dir / "checkpoints"
    tb_dir = self_play_dir / "tb"
    self_play_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    tb_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)
    checkpoint_paths: list[str] = []
    model: PPO | None = None

    for iteration in range(args.iterations):
        opponents = _choose_pool(
            checkpoint_paths, rng, num_suits=len(SUITS), env_config=env_config
        )
        vec_env = DummyVecEnv(
            [
                (
                    lambda rank=i: lambda: _make_env(
                        env_cfg,
                        seed=args.seed + 1000 * iteration + rank,
                        opponents=opponents,
                    )
                )()
                for i in range(int(train_cfg.get("n_envs", 4)))
            ]
        )

        if model is None:
            model = PPO(
                policy="MlpPolicy",
                env=vec_env,
                learning_rate=float(train_cfg["learning_rate"]),
                n_steps=int(train_cfg["n_steps"]),
                batch_size=int(train_cfg["batch_size"]),
                gamma=float(train_cfg["gamma"]),
                gae_lambda=float(train_cfg["gae_lambda"]),
                clip_range=float(train_cfg["clip_range"]),
                ent_coef=float(train_cfg["ent_coef"]),
                vf_coef=float(train_cfg["vf_coef"]),
                tensorboard_log=str(tb_dir),
                verbose=1,
                seed=args.seed,
            )
        else:
            model.set_env(vec_env)

        model.learn(total_timesteps=args.chunk_timesteps, reset_num_timesteps=False, progress_bar=True)
        ckpt_path = ckpt_dir / f"iter_{iteration:03d}"
        model.save(str(ckpt_path))
        context = build_training_metadata(
            config_path=args.config,
            config=cfg,
            observation_shape=tuple(vec_env.observation_space.shape),
            seeds={
                "model_seed": args.seed,
                "opponent_sampling_seed": args.seed,
                "vector_env_seeds": [
                    args.seed + 1000 * iteration + rank
                    for rank in range(vec_env.num_envs)
                ],
            },
            training_settings={
                key: value for key, value in train_cfg.items()
                if key not in {
                    "eval_freq", "n_eval_episodes", "deterministic_eval", "validation_seed",
                    "total_timesteps",
                }
            } | {"iterations": args.iterations, "chunk_timesteps": args.chunk_timesteps},
        )
        write_model_metadata(
            ckpt_path, role="self_play_checkpoint", context=context,
            checkpoint_selection=None,
            extra={"self_play": {"iteration": iteration, "timesteps": model.num_timesteps}},
        )
        checkpoint_paths.append(str(ckpt_path) + ".zip")
        vec_env.close()

    if model is not None:
        final_path = self_play_dir / "final_self_play_model"
        model.save(str(final_path))
        write_model_metadata(
            final_path, role="final_self_play_model", context=context,
            checkpoint_selection=None,
            extra={"self_play": {"iterations": args.iterations, "timesteps": model.num_timesteps}},
        )


if __name__ == "__main__":
    main()
