# Figgie Learning Lab (`figgie-rl`)

An open **reinforcement-learning lab for Figgie**: explore trading strategies,
train PPO agents, and study learning under hidden information.

**[Open the live lab](https://riversandrew36.github.io/figgie-rl/)** ·
[Train your first agent](docs/RL_QUICKSTART.md)

- **Watch and learn:** the browser arena seats four scripted baselines, supports
  seeded scenarios and pause/step, and explains settlement and initial-hand beliefs.
- **Train and evaluate:** the Python Gymnasium environment supports PPO, engineered
  belief features, paired baseline benchmarks, checkpoint metadata, and self-play.
- **Reproduce and question:** use separate validation and final-test seeds, export
  results, and read the [experiment records and limitations](docs/PROJECT_STATUS.md).

The browser and Python are separate simulations. The hosted viewer does **not** run
PPO checkpoints. The browser uses simplified external quotes/fills; Python also
supports a player-quote market. Seeds and outcomes do not transfer between them.
No validated claim of stronger PPO play in the newer player-quote market is made.

Start with the [RL quickstart](docs/RL_QUICKSTART.md) for a small train/evaluate
experiment, or run `figgie-arena` locally after installation below. The public demo is hosted on GitHub Pages; see
[deployment instructions](docs/DEPLOYMENT.md) for setup, checks, and rollback.

Independent educational implementation of [Figgie, created by Jane Street](https://www.figgie.com/).
Not affiliated with or endorsed by Jane Street. [Watch Jane Street's gameplay video](https://www.youtube.com/watch?v=q2jjJudrEnc&t=13s).
Code: [MIT](LICENSE). [Contribute](CONTRIBUTING.md).

## Quickstart

1. Create and activate a virtual environment.
2. Install the package:
   - Runtime install, including a built wheel: `pip install .`
   - Editable install with tests and lint: `pip install -e ".[dev]"`
   - A normal install exposes `figgie-train`, `figgie-eval`, `figgie-self-play`, `figgie-demo`, and `figgie-arena`. The browser assets are package data, so `figgie-arena` works from the installed distribution and does not need an editable checkout.
3. Train PPO with goal-suit belief features and bankroll-based checkpoint selection:
   - `figgie-train --config configs/ppo_simple.yaml`
   - The run writes `best_model.metadata.json` beside `best_model.zip` and `final_model.metadata.json` beside `final_model.zip`.
4. Evaluate the best bankroll checkpoint:
   - `figgie-eval --model-path artifacts/ppo_goal_belief_v2/best_model/best_model.zip --config configs/ppo_simple.yaml --episodes 200 --benchmark`
   - The benchmark compares PPO with hold, random, market-maker, value-trader, Bayesian goal-trader, and the four playing styles (hunter, banker, detective, bluffer) on the same episode seeds and reports paired profit differences.
   - Save that report with `--output results.json` or `--output results.csv`. Omit `--output` to keep the previous print-only behavior.
5. Run staged self-play:
   - `figgie-self-play --config configs/ppo_self_play.yaml --iterations 6 --chunk-timesteps 100000`
6. Inspect the environment interactively:
   - `figgie-demo --seed 7 --steps 5`
7. Run the browser arena:
   - `figgie-arena`
   - Open `http://127.0.0.1:8000/figgie_play.html`
   - The page, stylesheet, and script are read from the installed `figgie_rl.arena` package. Opening `figgie_rl/arena/figgie_play.html` directly also works, because the CSS and JS sit beside it.

## Playing styles

Four opponents with distinct personalities live in `figgie_rl/agents/styles.py`. The browser arena seats the same four.

| Label | Style | How it plays |
|---|---|---|
| `hunter` | Aggressive collector | Trusts its hand's goal-suit odds and lifts offers early to corner the goal suit and the majority pot. |
| `banker` | Market maker | Quotes both sides around a fair value from its hand, skews prices to flatten inventory, and only crosses for clear mispricings. |
| `detective` | Tape reader | Waits, updates its goal belief from other players' aggressive buying over the round, then follows the informed buyers. |
| `bluffer` | Deceiver | Buys a decoy suit early to fake demand, sells into it later, fades crowded suits, and bids quietly in its real target. |

Use any three as training opponents with `opponent_difficulties`, for example `[hunter, detective, bluffer]`. Opponent views include `cumulative_signed_flow`, the round's net aggressor volume per suit, which the detective and bluffer read.

## Project Layout

- `figgie_rl/envs/`: environment and game mechanics
- `figgie_rl/agents/`: scripted baseline opponents and the four playing styles
- `figgie_rl/train/`: training, evaluation, and model-metadata helpers
- `figgie_rl/arena/`: packaged browser arena seating the four playing styles (`figgie_play.html`, `figgie_arena.css`, `figgie_arena.js`)
- `figgie_play.py`: local server for those arena assets
- `configs/`: training configs
- `tests/`: mechanics, API, packaging, and output-format checks
- `.github/workflows/ci.yml`: test, lint, wheel, and clean-install smoke checks

## Benchmark output files

`figgie-eval --output PATH` writes the same evaluation it prints. The path suffix selects the format.

JSON (`results.json`) is one document with:

- `model_path`, `config_path`, `benchmark`, `episodes`, and `base_seed`
- `seeds` and `agent_rng_seeds` for each episode
- `policies`
- `configuration`, including starting cash, the resolved environment, and the loaded YAML
- `per_episode` rows with profit, win, tie, rank, bankroll, drawdown, inventory risk, quote fill rate, and spread capture
- `aggregates` for each policy
- `paired_profit_differences` against PPO when `--benchmark` is set: mean difference, approximate 95% interval, and the fraction of episodes where PPO's profit was higher

CSV (`results.csv`) writes that same information across four files:

- `results.csv`: one row per episode and policy
- `results.aggregates.csv`: one row per policy
- `results.paired.csv`: paired profit differences
- `results.meta.csv`: seeds, policy names, paths, and the configuration JSON

Aggregate profit intervals use `1.96 * population_stdev / sqrt(n)`. Paired intervals use `1.96 * sample_stdev / sqrt(n)`, matching the printed report. Profit is final bankroll minus starting cash.

## Training metadata

`figgie-train` writes a JSON sidecar beside each model artifact:

- `artifacts/<run>/best_model/best_model.metadata.json` next to the selected checkpoint
- `artifacts/<run>/models/final_model.metadata.json` next to the final weights

Each file contains:

- the resolved config, with environment defaults filled in. `env.seed` stays unset unless the YAML sets it; the seeds actually used for training and validation are recorded separately
- random seeds: training seed, model seed, vector-environment seeds, validation seed, and validation episode seeds
- the Python version and the installed versions of `figgie-rl`, `gymnasium`, `numpy`, `PyYAML`, `stable-baselines3`, `torch`, `tqdm`, and `rich`
- the observation shape
- the training settings passed to PPO and the bankroll callback
- checkpoint-selection metrics for the retained best checkpoint: timesteps, mean final bankroll, mean profit, win rate, mean rank, validation episodes, and the lexicographic rule (higher mean final bankroll, then higher win rate, then lower mean rank)

The best-model sidecar is replaced whenever a later checkpoint wins selection. The final-model sidecar describes the end-of-training weights, repeats those selection metrics, and records how many timesteps were requested and completed. `best_model.zip` is still the selected checkpoint. `final_model.zip` is still the weights at the end of training. The per-checkpoint log remains `eval_logs/bankroll_evaluations.csv`.

`figgie-self-play` saves the same metadata sidecars for each iteration and the final model, including the resolved observation/market settings and iteration seeds. It saves every iteration without bankroll checkpoint selection, so `checkpoint_selection` is null.

## Validation and final testing

The standard and player-quote configs now select checkpoints using 200 fixed validation episodes (seeds 50007–50206), every 20,000 training timesteps. A 120,000-step run therefore makes six selections instead of 24 selections on 20 episodes. The smoke config deliberately retains a small, quick validation set. Self-play saves every iteration and does not run the validation settings in its YAML.

The `evaluation` block reserves seeds 700000–700999 for a 1,000-episode final test. Training checks that this range does not overlap validation and does not run it. Exploratory evaluation retains the default 200 episodes starting at seed 101. After choosing a checkpoint and freezing the experiment, run:

```bash
figgie-eval --model-path artifacts/ppo_goal_belief_v2/best_model/best_model.zip \
  --config configs/ppo_simple.yaml --test --benchmark --output results/final_test.json
```

`--test` uses the configured range and rejects simultaneous `--seed` or `--episodes` overrides. Reports record `configuration.evaluation_split` as `test` or `exploratory`. A larger validation set reduces selection noise; repeated selection still creates optimism, so use the final test for reporting rather than tuning. After examining that test, reserve fresh seeds for future experiments.

The updated standard config uses `run_name: ppo_goal_belief_v2`, preserving the historical `ppo_goal_belief` artifacts. No full v2 training or reserved final test has been run yet.

## Player-quote market and self-play

`configs/endogenous_market.yaml` enables `market_mode: endogenous`: only player quotes provide liquidity, quotes use an absolute $1–$60 ladder, and an empty book cannot force a random holder to trade. Observations append four bid-availability and four ask-availability flags; inactive prices are zero in network input. The historical exogenous market remains the default and uses its outside book.

Run self-play in the player-quote market with:

```bash
figgie-self-play --config configs/endogenous_market.yaml --iterations 6 --chunk-timesteps 100000
```

Self-play honors the configured belief-feature flags and scripted lineup; once checkpoints exist, its third opponent becomes a sampled frozen policy. Without an explicit lineup, endogenous mode starts with two reservation market makers and a Bayesian trader. Frozen policies restore market and feature settings from metadata, check the observation and action spaces, and decode actions with the correct market's action table. Older checkpoints without sidecars use their action count to identify the market. A single optional feature group in an old checkpoint is assumed to be order flow; a goal-only model without metadata requires an explicit `EnvConfig` when constructing `FrozenPPOOpponent`.

## Continuous integration

`.github/workflows/ci.yml` runs on push and pull request:

- `ruff check .`
- `python -m pytest -q`
- `python -m build --wheel`
- install that wheel into a clean virtual environment
- smoke-test the installed CLI commands and confirm the arena HTML, CSS, and JS are served from the installed package

Local equivalents, from an editable dev install:

```bash
ruff check .
python -m pytest -q
```

## What The Agent Observes

Each observation is a flat vector containing:

- inventory by suit
- cash
- current market best bid/ask by suit
- the agent's own outstanding bid/ask quotes
- last trade price and signed trade flow by suit
- time remaining and step fraction
- optional belief-like features derived from recent order flow
- optional Bayesian goal-suit probabilities derived from the agent's initial hand

This makes the environment easier to study and also produces a cleaner training signal than hiding basic market state.

## How Rewards Work

Each environment step returns a reward with three conceptual pieces:

- `trade_reward`: immediate cashflow and mark-to-market effect from trades on the current book
- `inventory_reward`: revaluation after the external market drifts to the next step
- `settlement_reward`: terminal value of goal-suit cards plus the majority bonus

The environment now applies market drift after actions, so the agent is not incorrectly rewarded or penalized for exogenous price movement that happened before it had a chance to act.
It also includes a configurable external order-flow process that can lift the best ask or hit the best bid, which makes passive quoting and spread capture learnable during PPO training.
Quotes can join or improve the displayed market and expire after a configurable TTL. Probabilistic liquidity always selects another player as the counterparty, preserving the 40-card deck and trading cash.

At the natural round horizon, marked inventory is replaced by its true settlement payoff. With pot-conserving settlement enabled, players start with cash, post antes, goal cards receive their configured payout, and the majority winner(s) split the remainder of the pot.

## Educational Use

- `figgie-demo` prints the action table, observation layout, hidden round metadata, and a sample rollout with reward breakdowns.
- `info["observation_spec"]` and `info["action_meanings"]` are returned on reset for easier debugging and notebook exploration.
- `info["reward_breakdown"]` is returned on each step so you can inspect why a reward changed.
- Terminal info includes all final bankrolls, the learning agent's rank, and winner indices.
- The browser arena supports deterministic seeds, pause/single-step, speed control, quote ownership, and JSON round-log downloads.

## Roadmap

- Baseline PPO on simplified market dynamics
- Belief-augmented observations for hidden-information inference
- Opponent-pool self-play with recurrent policy support
- Richer market microstructure approximation

## Notes On Phase-5 Upgrade

- `SimpleFiggieEnv` supports optional belief-like flow features via `include_belief_features`.
- `include_goal_belief_features` adds private hand-derived probabilities without exposing the hidden goal label.
- `figgie_rl/train/self_play.py` rotates opponents between scripted baselines and frozen PPO checkpoints.
- This creates a practical bridge from fixed-opponent learning to non-stationary self-play.

## Current Experiment Notes

- See [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) for the goal-inference implementation, bankroll checkpoint-selection method, latest training and benchmark results, commands, and known limitations.
