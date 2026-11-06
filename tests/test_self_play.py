import numpy as np
import json
import sys
from dataclasses import asdict

import pytest
import yaml
from stable_baselines3 import PPO

from figgie_rl.agents.baselines import OpponentAction, OpponentView
from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.train.self_play import FrozenPPOOpponent, main


def test_frozen_ppo_opponent_uses_model_observation_shape(tmp_path) -> None:
    env = SimpleFiggieEnv(EnvConfig(include_belief_features=True, seed=4))
    model = PPO("MlpPolicy", env, n_steps=8, batch_size=8, verbose=0)
    model_path = tmp_path / "belief_model"
    model.save(model_path)

    frozen = FrozenPPOOpponent(str(model_path) + ".zip", num_suits=4)
    view = OpponentView(
        inventory=np.ones(4, dtype=np.int32),
        cash=300.0,
        best_bid=np.full(4, 4.0),
        best_ask=np.full(4, 6.0),
        own_bid_quote=np.full(4, -np.inf),
        own_ask_quote=np.full(4, np.inf),
        last_trade_price=np.full(4, 5.0),
        last_trade_signed_volume=np.zeros(4),
        belief_flow=np.zeros(4),
        time_remaining=1.0,
        step=0,
        max_steps=10,
    )

    obs = frozen._obs_from_view(view)
    assert obs.shape == env.observation_space.shape == (35,)
    action = frozen.act(view, np.random.default_rng(1))
    assert action.kind in {"hold", "buy", "sell", "quote_bid", "quote_ask"}


@pytest.mark.parametrize("market_mode", ["exogenous", "endogenous"])
@pytest.mark.parametrize("flow,goal", [(False, False), (True, False), (False, True), (True, True)])
def test_frozen_observation_matches_every_seat_and_feature_layout(
    tmp_path, market_mode, flow, goal
) -> None:
    config = EnvConfig(
        market_mode=market_mode,
        include_belief_features=flow,
        include_goal_belief_features=goal,
    )
    env = SimpleFiggieEnv(config)
    env.reset(seed=12)
    model = PPO("MlpPolicy", env, n_steps=8, batch_size=8, verbose=0)
    path = tmp_path / "policy"
    model.save(path)
    path.with_suffix(".metadata.json").write_text(
        json.dumps({"resolved_config": {"env": asdict(config)}})
    )
    frozen = FrozenPPOOpponent(str(path), num_suits=4)
    for active_book in (False, True):
        if active_book:
            env._apply_semantic_action(0, OpponentAction("quote_bid", suit=0, limit_price=8))
            env._apply_semantic_action(1, OpponentAction("quote_ask", suit=1, limit_price=12))
        for seat in range(4):
            np.testing.assert_allclose(
                frozen._obs_from_view(env._opponent_view(seat)), env._build_observation(seat)
            )
    env.close()


@pytest.mark.parametrize("flow,goal", [(False, False), (True, False), (True, True)])
def test_endogenous_checkpoint_without_sidecar_decodes_absolute_quotes(tmp_path, flow, goal) -> None:
    env = SimpleFiggieEnv(EnvConfig(
        market_mode="endogenous", include_belief_features=flow, include_goal_belief_features=goal
    ))
    env.reset(seed=9)
    path = tmp_path / "policy"
    PPO("MlpPolicy", env, n_steps=8, batch_size=8, verbose=0).save(path)
    frozen = FrozenPPOOpponent(str(path), num_suits=4)
    action_index = env.encode_semantic_action(OpponentAction("quote_ask", suit=3, limit_price=60))
    frozen.model.predict = lambda *args, **kwargs: (np.array(action_index), None)
    action = frozen.act(env._opponent_view(env.agent_idx), np.random.default_rng(3))
    assert action.kind == "quote_ask"
    assert action.suit == 3
    assert action.limit_price == 60
    np.testing.assert_allclose(
        frozen._obs_from_view(env._opponent_view(env.agent_idx)), env._build_observation(env.agent_idx)
    )
    with pytest.raises(ValueError, match="schema"):
        FrozenPPOOpponent(str(path), num_suits=4, env_config=EnvConfig())
    env.close()


@pytest.mark.parametrize("include_features", [False, True])
def test_two_iteration_endogenous_self_play_reloads_its_checkpoint(
    tmp_path, monkeypatch, include_features
) -> None:
    config = {
        "run_name": "self_play_smoke",
        "env": {
            "market_mode": "endogenous", "max_steps": 4,
            "include_belief_features": include_features,
            "include_goal_belief_features": include_features,
            "opponent_difficulties": ["reservation", "reservation", "bayesian"],
        },
        "train": {
            "n_envs": 2, "learning_rate": 0.0003, "n_steps": 8, "batch_size": 8,
            "gamma": 0.99, "gae_lambda": 0.95, "clip_range": 0.2,
            "ent_coef": 0.01, "vf_coef": 0.5,
        },
        "paths": {"root_artifacts": str(tmp_path / "artifacts")},
    }
    config_path = tmp_path / "self_play.yaml"
    config_path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(sys, "argv", [
        "figgie-self-play", "--config", str(config_path), "--iterations", "2",
        "--chunk-timesteps", "16", "--seed", "19",
    ])
    main()
    run = tmp_path / "artifacts" / "self_play_smoke" / "self_play"
    for stem in (run / "checkpoints" / "iter_000", run / "checkpoints" / "iter_001",
                 run / "final_self_play_model"):
        metadata = json.loads(stem.with_suffix(".metadata.json").read_text())
        assert metadata["resolved_config"]["env"]["include_belief_features"] == include_features
        assert metadata["observation_shape"] == [47 if include_features else 39]
        assert metadata["checkpoint_selection"] is None
        frozen = FrozenPPOOpponent(str(stem), num_suits=4)
        assert frozen.config.market_mode == "endogenous"
        assert frozen.model.action_space.n == 105
