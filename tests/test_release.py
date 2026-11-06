"""Release contracts: a static-only payload and a valid small RL workflow."""

from pathlib import Path
import runpy

import yaml

from figgie_rl.envs.simple_figgie_env import EnvConfig, SimpleFiggieEnv
from figgie_rl.train.metadata import resolve_test_settings, resolve_training_settings
from figgie_rl.train.train_ppo import validate_train_config

ROOT = Path(__file__).resolve().parents[1]


def test_pages_contains_only_browser_assets(tmp_path: Path) -> None:
    build = runpy.run_path(str(ROOT / "scripts" / "build_pages.py"))["build"]
    build(tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {
        "index.html", "figgie_arena.css", "figgie_arena.js",
    }
    html = (tmp_path / "index.html").read_text()
    assert 'href="figgie_arena.css"' in html
    assert 'src="figgie_arena.js"' in html
    assert 'href="/figgie_arena.css"' not in html


def test_learning_config_has_distinct_splits_and_valid_environment() -> None:
    cfg = yaml.safe_load((ROOT / "configs" / "ppo_learning.yaml").read_text())
    validate_train_config(cfg["train"])
    settings = resolve_training_settings(cfg["train"], cfg["seed"])
    resolve_test_settings(cfg)
    validation = set(range(settings["validation_seed"],
                           settings["validation_seed"] + settings["n_eval_episodes"]))
    exploratory = set(range(610000, 610050))
    final = set(range(cfg["evaluation"]["test_seed"],
                      cfg["evaluation"]["test_seed"] + cfg["evaluation"]["test_episodes"]))
    assert not (validation & exploratory or validation & final or exploratory & final)
    env = SimpleFiggieEnv(EnvConfig(**cfg["env"]))
    obs, _ = env.reset(seed=cfg["seed"])
    assert env.observation_space.contains(obs)
    assert env.action_space.n == 105
    env.close()
