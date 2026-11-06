"""Train a PPO agent on the simplified Figgie environment."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.train.metadata import (
    CHECKPOINT_SELECTION_RULE,
    build_training_metadata,
    resolve_training_settings,
    resolve_test_settings,
    write_model_metadata,
)


class BankrollEvalCallback(BaseCallback):
    """Select checkpoints by held-out final bankroll, then win rate and rank."""

    def __init__(
        self,
        env_cfg: dict[str, Any],
        eval_freq: int,
        episodes: int,
        seed: int,
        best_model_path: Path,
        log_path: Path,
        metadata_context: dict[str, Any],
        deterministic: bool = True,
    ) -> None:
        super().__init__(verbose=0)
        self.eval_env = make_env(env_cfg, seed=seed)
        self.eval_freq = int(eval_freq)
        self.episodes = int(episodes)
        self.seed = int(seed)
        self.best_model_path = best_model_path
        self.log_path = log_path
        self.metadata_context = metadata_context
        self.deterministic = deterministic
        self.next_eval_timestep = self.eval_freq
        self.best_key = (-float("inf"), -float("inf"), -float("inf"))
        self.best_selection: dict[str, Any] | None = None
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(
                handle,
                fieldnames=(
                    "timesteps", "mean_final_bankroll", "mean_profit", "win_rate",
                    "mean_rank", "episodes",
                ),
            ).writeheader()

    def _evaluate(self) -> dict[str, float]:
        bankrolls: list[float] = []
        ranks: list[int] = []
        wins = 0
        for episode in range(self.episodes):
            obs, _ = self.eval_env.reset(seed=self.seed + episode)
            done = False
            info: dict[str, Any] = {}
            while not done:
                action, _ = self.model.predict(obs, deterministic=self.deterministic)
                obs, _, terminated, truncated, info = self.eval_env.step(int(action))
                done = terminated or truncated
            bankrolls.append(float(info["final_bankroll"]))
            ranks.append(int(info["final_rank"]))
            wins += int(info["winner_indices"] == [self.eval_env.agent_idx])

        return {
            "mean_final_bankroll": float(sum(bankrolls) / len(bankrolls)),
            "mean_profit": float(
                sum(bankrolls) / len(bankrolls) - self.eval_env.config.starting_cash
            ),
            "win_rate": float(wins / self.episodes),
            "mean_rank": float(sum(ranks) / len(ranks)),
        }

    def _on_step(self) -> bool:
        if self.num_timesteps < self.next_eval_timestep:
            return True
        while self.next_eval_timestep <= self.num_timesteps:
            self.next_eval_timestep += self.eval_freq

        metrics = self._evaluate()
        record = {"timesteps": self.num_timesteps, **metrics, "episodes": self.episodes}
        with self.log_path.open("a", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=record.keys()).writerow(record)
        self.logger.record("eval/mean_final_bankroll", metrics["mean_final_bankroll"])
        self.logger.record("eval/mean_profit", metrics["mean_profit"])
        self.logger.record("eval/win_rate", metrics["win_rate"])
        self.logger.record("eval/mean_rank", metrics["mean_rank"])

        selection_key = (
            metrics["mean_final_bankroll"],
            metrics["win_rate"],
            -metrics["mean_rank"],
        )
        if selection_key > self.best_key:
            self.best_key = selection_key
            self.model.save(str(self.best_model_path))
            self.best_selection = {
                "timesteps": int(self.num_timesteps),
                "mean_final_bankroll": float(metrics["mean_final_bankroll"]),
                "mean_profit": float(metrics["mean_profit"]),
                "win_rate": float(metrics["win_rate"]),
                "mean_rank": float(metrics["mean_rank"]),
                "episodes": int(self.episodes),
                "validation_seed": int(self.seed),
                "deterministic": bool(self.deterministic),
                "selection_rule": CHECKPOINT_SELECTION_RULE,
            }
            write_model_metadata(
                self.best_model_path,
                role="best_model",
                context=self.metadata_context,
                checkpoint_selection=self.best_selection,
            )
        print(
            f"Bankroll eval at {self.num_timesteps} steps: "
            f"profit={metrics['mean_profit']:.2f}, win={metrics['win_rate']:.3f}, "
            f"rank={metrics['mean_rank']:.3f}"
        )
        return True

    def _on_training_end(self) -> None:
        self.eval_env.close()


def load_config(config_path: str) -> dict[str, Any]:
    with Path(config_path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def make_env(env_cfg: dict[str, Any], seed: int | None = None) -> SimpleFiggieEnv:
    cfg = EnvConfig(**(dict(env_cfg) | {"seed": seed}))
    env = SimpleFiggieEnv(config=cfg)
    return env


def build_vec_env(env_cfg: dict[str, Any], n_envs: int, seed: int) -> DummyVecEnv:
    def make_one(rank: int):
        def thunk():
            env = make_env(env_cfg, seed=seed + rank)
            return Monitor(env)

        return thunk

    return DummyVecEnv([make_one(i) for i in range(n_envs)])


def validate_train_config(train_cfg: dict[str, Any]) -> None:
    if int(train_cfg["total_timesteps"]) <= 0:
        raise ValueError("train.total_timesteps must be > 0")
    if int(train_cfg["n_envs"]) <= 0:
        raise ValueError("train.n_envs must be > 0")
    if int(train_cfg["n_steps"]) <= 0:
        raise ValueError("train.n_steps must be > 0")
    if int(train_cfg["batch_size"]) <= 0:
        raise ValueError("train.batch_size must be > 0")
    if int(train_cfg["eval_freq"]) <= 0 or int(train_cfg["n_eval_episodes"]) <= 0:
        raise ValueError("train.eval_freq and train.n_eval_episodes must be > 0")
    rollout_size = int(train_cfg["n_steps"]) * int(train_cfg["n_envs"])
    if int(train_cfg["batch_size"]) > rollout_size:
        raise ValueError("train.batch_size cannot exceed n_steps * n_envs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train PPO for simplified Figgie.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/ppo_simple.yaml",
        help="Path to YAML config.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    run_name = cfg.get("run_name", "ppo_simple")
    seed = int(cfg.get("seed", 7))
    env_cfg = cfg["env"]
    train_cfg = cfg["train"]
    paths = cfg.get("paths", {})
    validate_train_config(train_cfg)
    if cfg.get("evaluation"):
        resolve_test_settings(cfg)
    training_settings = resolve_training_settings(train_cfg, seed)

    root_artifacts = Path(paths.get("root_artifacts", "artifacts"))
    run_dir = root_artifacts / run_name
    model_dir = run_dir / "models"
    best_dir = run_dir / "best_model"
    tb_dir = run_dir / "tb"
    eval_log_dir = run_dir / "eval_logs"

    for folder in (model_dir, best_dir, tb_dir, eval_log_dir):
        folder.mkdir(parents=True, exist_ok=True)

    vec_env = build_vec_env(env_cfg, n_envs=training_settings["n_envs"], seed=seed)
    validation_seed = training_settings["validation_seed"]
    metadata_context = build_training_metadata(
        config_path=args.config,
        config=cfg,
        observation_shape=tuple(vec_env.observation_space.shape),
        seeds={
            "training_seed": seed,
            "model_seed": seed,
            "vector_env_seeds": [seed + rank for rank in range(training_settings["n_envs"])],
            "validation_seed": validation_seed,
            "validation_episode_seeds": [
                validation_seed + episode
                for episode in range(training_settings["n_eval_episodes"])
            ],
        },
        training_settings=training_settings,
    )

    model = PPO(
        policy=training_settings["policy"],
        env=vec_env,
        learning_rate=training_settings["learning_rate"],
        n_steps=training_settings["n_steps"],
        batch_size=training_settings["batch_size"],
        gamma=training_settings["gamma"],
        gae_lambda=training_settings["gae_lambda"],
        clip_range=training_settings["clip_range"],
        ent_coef=training_settings["ent_coef"],
        vf_coef=training_settings["vf_coef"],
        tensorboard_log=str(tb_dir),
        verbose=1,
        seed=seed,
    )

    best_model_stem = best_dir / "best_model"
    eval_callback = BankrollEvalCallback(
        env_cfg=env_cfg,
        eval_freq=training_settings["eval_freq"],
        episodes=training_settings["n_eval_episodes"],
        seed=validation_seed,
        best_model_path=best_model_stem,
        log_path=eval_log_dir / "bankroll_evaluations.csv",
        metadata_context=metadata_context,
        deterministic=training_settings["deterministic_eval"],
    )

    total_timesteps = training_settings["total_timesteps"]
    model.learn(total_timesteps=total_timesteps, callback=eval_callback, progress_bar=True)
    final_model_stem = model_dir / "final_model"
    model.save(str(final_model_stem))
    write_model_metadata(
        final_model_stem,
        role="final_model",
        context=metadata_context,
        checkpoint_selection=eval_callback.best_selection,
        extra={
            "training_result": {
                "total_timesteps_requested": total_timesteps,
                "timesteps_completed": int(model.num_timesteps),
                "best_checkpoint_timesteps": None
                if eval_callback.best_selection is None
                else eval_callback.best_selection["timesteps"],
            }
        },
    )

    vec_env.close()


if __name__ == "__main__":
    main()
