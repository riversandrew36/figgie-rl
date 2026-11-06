# Project status: market integration, validation, and experiment records

Updated October 12, 2026. This is the handoff for resuming the project. Historical training results below are preserved and are not evidence of performance in the new player-quote market.

## Learning Lab release verification — November 6, 2026

The release adds an RL-first browser entry point, settlement explanations, shared
scenarios, and a local training guide. Browser bots remain scripted; the JavaScript
simulation does not execute Python policies.

The new `configs/ppo_learning.yaml` completed its 4,096-step workflow demonstration
from a wheel installed in a clean temporary environment. A 50-episode exploratory
benchmark on seeds 610000–610049 exported successfully. This is an installation and
workflow check, not a claim of competitive learned play. Validation seeds
600000–600019 were used for checkpoint selection. Reserved final seeds
620000–620199 remain untouched. The historical full v2 training and its reserved
final test below remain outstanding. Generated models and reports stay local.

## Current state

- Arena packaging, JSON/CSV benchmark exports, PPO metadata sidecars, and CI are implemented.
- The environment has two market modes: the historical outside-book (`exogenous`) mode and player-quote (`endogenous`) mode. The latter has no forced fills or random outside order flow. It uses a 12-rung absolute quote ladder from $1 to $60 and requires a real player quote for a trade.
- Hunter, banker, detective, and bluffer styles quote according to their hand/tape estimates. Reservation market makers provide another price-aware opponent. Legacy weak/average/tough policies still use a fixed quote shim and can be exploited in the new market.
- Frozen self-play now handles both market modes, restores feature settings from checkpoint metadata, and reconstructs bounded prices plus availability flags for empty books. It honors explicit feature flags and the configured opponent lineup, replacing the third scripted opponent with a frozen checkpoint after iteration zero. Without a configured lineup, endogenous self-play starts with two reservation market makers and a Bayesian trader.
- Every self-play checkpoint and final model now has a metadata sidecar. Self-play saves each iteration without bankroll selection; `checkpoint_selection` is null.
- Standard PPO and endogenous configs now validate on 200 episodes every 20,000 training timesteps. Validation seeds are 50007–50206. The smoke config remains intentionally small. The self-play CLI does not use its YAML validation settings.
- The configs reserve final-test seeds 700000–700999. Training rejects validation/test overlap and never executes the final test. The evaluator's `--test` option selects the reserved range, rejects seed/count overrides, and labels the report as a test result.
- The standard config now writes to `artifacts/ppo_goal_belief_v2/` to preserve the earlier goal-belief checkpoint. No full v2 run or reserved final test has been performed.

## Player-quote diagnostic evidence

`artifacts/goal_buy_diagnostic.json` is the initial 200-episode diagnostic on seeds 900000–900199. `artifacts/goal_buy_diagnostic_phase2.json` extends the opponent comparisons on seeds 900200–900399. These are game-design diagnostics using scripted agents, not PPO test results. Reproducing a diagnostic after code changes may produce different values; the files record the earlier runs.

Mean profit in the saved phase-two diagnostic:

| Market / opponents | Hold | Naive goal buyer | Bayesian |
|---|---:|---:|---:|
| Outside book / weak, average, tough | −$2.88 | +$11.39 | +$25.43 |
| Player quotes / legacy weak, average, tough | −$15.23 | −$68.60 | +$112.23 |
| Player quotes / three reservation makers | −$13.05 | −$105.37 | +$10.81 |
| Player quotes / hunter, banker, detective | −$5.90 | −$46.92 | +$13.88 |
| Player quotes / banker, detective, bluffer | −$3.58 | −$54.56 | +$6.44 |

Blindly buying the most likely goal suit at any price loses substantially in the player-quote market. The Bayesian trader still profits, but its very large gain against legacy quoters shrinks against price-aware opponents. This supports using reservation/style opponents when assessing the new market rather than interpreting exploitation of the legacy quote shim as learned Figgie skill.

## Resume commands

Check the code and wheel packaging:

```bash
ruff check .
python3 -m pytest -q
```

Start a standard PPO run with the larger validation set:

```bash
python3 -m figgie_rl.train.train_ppo --config configs/ppo_simple.yaml
```

Start endogenous self-play (this is a substantial training run, not a smoke check):

```bash
python3 -m figgie_rl.train.self_play --config configs/endogenous_market.yaml \
  --iterations 6 --chunk-timesteps 100000
```

After freezing the standard experiment, run the reserved final test once and save its report:

```bash
python3 -m figgie_rl.train.evaluate \
  --model-path artifacts/ppo_goal_belief_v2/best_model/best_model.zip \
  --config configs/ppo_simple.yaml --test --benchmark --output results/final_test.json
```

Use the matching market config when evaluating an endogenous checkpoint. Diagnostic seeds 900000–900399 and historical exploratory seeds 101–300 have already been examined; do not relabel them as untouched test data. Once the reserved test has influenced a development decision, choose a fresh range for the next final test.

## Compatibility and verification

Exogenous models have 33 actions and 31/35/39 observation elements. Endogenous models have 105 actions and 39/43/47 elements. Observation length alone cannot identify the schema. The adapter prefers the sidecar's resolved environment; it checks both spaces and rejects mismatched market/feature settings. For old models without metadata, action count disambiguates market mode. An old one-group layout defaults to flow features; supply an explicit `EnvConfig` for a goal-only checkpoint without a sidecar.

Regression coverage includes observation parity for every seat in both market modes with all feature combinations, empty and populated books, decoding quotes above the old action range, and a two-iteration endogenous self-play run that reloads its first checkpoint. The final-test CLI is exercised on synthetic seeds, leaving the real reserved range untouched. Validation/test overlap is rejected before training or final-test evaluation.

Verification on October 12: Ruff passed. The full suite passed 79 tests inside the sandbox; the remaining arena HTTP test was blocked from binding localhost and passed when rerun with socket access (80 tests verified in total). No substantial new training run was started as part of these integration changes.

## Historical goal-inference experiment

The following sections record the earlier 120,000-step run, its original 20-episode checkpoint selection, and its benchmark. Larger validation sets reduce noise but do not erase repeated-selection bias. No claim of improved PPO profitability follows from the integration fixes alone.

## What changed

### Hand-derived goal probabilities

`figgie_rl/envs/mechanics.py` now exposes `goal_suit_posterior(hand_inventory)`. The deck contains a uniformly permuted 12/10/10/8 suit distribution. For each possible 12-card heavy suit, the function enumerates the six assignments of 10/10/8 to the other suits. The likelihood of the observed ten-card hand under an assignment is proportional to the product of the four combinations `choose(deck_count, hand_count)`. It adds each heavy-suit likelihood to the same-color partner that defines the goal suit, then normalizes the four goal probabilities.

The calculation uses only the player's original private hand. It does not read or reveal the environment's hidden goal label. The environment preserves `initial_inventories` separately from tradable inventory, so later trades do not change this initial-hand posterior.

When `include_goal_belief_features` is enabled, the observation appends four probabilities in `SUITS` order. The standard config enables both these features and the existing order-flow features, making the observation length 39. `opponent_difficulties` accepts `bayesian`, and `BayesianGoalTrader` uses the same posterior to decide whether to buy or sell. It estimates a card's value as posterior goal probability times goal-card value plus a heuristic share of the majority bonus. This opponent is a useful benchmark, not an optimal strategy.

The standard training lineup is now weak random, average market maker, and Bayesian goal trader. Self-play also starts with a Bayesian goal trader when it has no frozen checkpoint yet. Frozen PPO adapters accept 31-, 35-, and 39-element observations; self-play's 35-element form means order-flow features only, while 39 means both feature groups.

### Checkpoint selection

`BankrollEvalCallback` in `figgie_rl/train/train_ppo.py` evaluates on deterministic validation seeds after each configured number of training timesteps. It records mean final bankroll, profit from starting cash, outright win rate, and mean rank in `artifacts/<run>/eval_logs/bankroll_evaluations.csv`.

Checkpoint selection is lexicographic: higher mean final bankroll wins; win rate breaks an exact bankroll tie; mean rank breaks a remaining tie. The chosen checkpoint is saved as `best_model/best_model.zip`, and the final training weights are saved separately as `models/final_model.zip`.

The validation set currently contains 20 fixed seeds (50007–50026 in the standard config). Repeatedly choosing among many checkpoints using the same small set can overfit checkpoint selection. The benchmark below is run on separate seeds and shows why that distinction matters. Treat validation scores as a selection aid, not as the final performance estimate.

## Historical training run

Command:

```bash
python3 -m figgie_rl.train.train_ppo --config configs/ppo_simple.yaml
```

The configured 120,000 steps completed at 120,832 environment timesteps because PPO collects complete rollouts across four environments. The best validation checkpoint was selected at 95,000 steps, where its 20-seed validation mean profit was +$24.62, win rate 40%, and mean rank 1.95. Other nearby validation points varied substantially; at 120,000 steps the 20-seed mean profit was −$3.95. Full per-checkpoint values are in `artifacts/ppo_goal_belief/eval_logs/bankroll_evaluations.csv`.

## Historical independent benchmark

Command:

```bash
python3 -m figgie_rl.train.evaluate \
  --model-path artifacts/ppo_goal_belief/best_model/best_model.zip \
  --config configs/ppo_simple.yaml --episodes 200 --benchmark
```

The evaluator uses seeds 101–300, rotating the learner seat, action order, and quote tie priority per episode. Profit is final bankroll minus the configured $350 starting cash. The run compared PPO with hold, random, market maker, value trader, and Bayesian goal trader against the same configured opponent lineup.

| Policy | Mean profit | Outright wins | Mean rank |
|---|---:|---:|---:|
| PPO | −$8.42 | 12.5% | 2.560 |
| Hold | −$9.07 | 10.5% | 2.545 |
| Random | −$36.53 | 11.5% | 3.155 |
| Market maker | +$3.05 | 16.5% | 2.365 |
| Value trader | −$15.04 | 20.0% | 2.925 |
| Bayesian | +$16.95 | 39.5% | 2.350 |

Paired profit differences compare policies episode by episode:

| PPO minus | Mean difference | Approx. 95% interval | Episodes PPO beat policy |
|---|---:|---:|---:|
| Hold | +$0.65 | [−$5.78, +$7.08] | 39.0% |
| Random | +$28.11 | [+$19.42, +$36.80] | 78.5% |
| Market maker | −$11.47 | [−$19.92, −$3.02] | 38.0% |
| Value trader | +$6.62 | [−$3.61, +$16.85] | 63.5% |
| Bayesian | −$25.36 | [−$36.25, −$14.47] | 47.0% |

The new PPO checkpoint clearly beats random, but does not beat the market maker or Bayesian policy on profit in this run. Most notably, its selected 20-seed validation profit (+$24.62) did not carry over to the independent 200-seed benchmark (−$8.42). This is strong evidence that the current 20-episode checkpoint selection is too noisy and is being selected optimistically. Do not interpret the validation score as a generalization result.

The 95% intervals are normal approximations over paired per-seed profit differences. They describe uncertainty for these policies, environment configuration, and opponent lineup; they do not establish performance against human players or full Figgie.

## Historical follow-up recommendations

1. The earlier goal-belief run used `run_name: ppo_goal_belief`. The current config uses `ppo_goal_belief_v2` and the stronger validation protocol described above.
2. Run a fresh independent benchmark with more episodes before changing training hyperparameters:

   ```bash
   python3 -m figgie_rl.train.evaluate \
     --model-path artifacts/ppo_goal_belief/best_model/best_model.zip \
     --config configs/ppo_simple.yaml --episodes 1000 --benchmark
   ```

3. The current configs increase validation episodes and reserve a separate final-test seed range. A future checkpoint tournament and multiple independent training seeds would further strengthen the comparison.
4. Once selection is stable, test longer training and opponent-pool self-play. The current Bayesian baseline already outperforms PPO, so compare against it explicitly in each run.

## Packaging and experiment records

These notes describe the current tooling. They do not replace the benchmark numbers above, which came from the printed evaluator and were not saved as a CSV or JSON report.

- `pip install .` installs the console scripts and the browser arena. `figgie-arena` serves `figgie_play.html`, `figgie_arena.css`, and `figgie_arena.js` from the installed package.
- `figgie-eval --output results.json` or `--output results.csv` writes per-episode rows, aggregate metrics, and paired profit differences, along with seeds, policy names, and the loaded configuration. See the README for the file layout.
- `figgie-train` writes `best_model.metadata.json` beside `best_model.zip` and `final_model.metadata.json` beside `final_model.zip`. Each file contains the resolved config, seeds, Python and dependency versions, observation shape, training settings, and the checkpoint-selection metrics for the retained best checkpoint. Artifacts already in `artifacts/ppo_goal_belief/` predate those sidecars.
- Continuous integration runs the test suite, `ruff check`, a wheel build, a clean-environment install, and smoke tests of the installed CLIs and arena assets.
- Self-play checkpoints now get metadata sidecars; they still do not use bankroll checkpoint selection.

## Known limits

- In exogenous mode the outside mid-price still drifts independently of the hidden goal. Endogenous mode removes that book and lets player quotes determine prices.
- The Bayesian opponent uses a simple majority-bonus heuristic and does not update its posterior from public trades. It provides a learnable, interpretable target rather than a solved game strategy.
- Historical validation reused 20 seeds across 24 checkpoints. Current configs use 200 seeds and six selection points over 120,000 steps. Repeated validation can still select optimistically; report the separate final test and results across training seeds.
- The browser arena remains a separate JavaScript implementation, now packaged under `figgie_rl/arena/`, and does not load these Python policies.
- Run `python3 -m pytest -q` before merging or releasing. Tests were not run during the goal-inference implementation session recorded above. The CI workflow now runs the suite, lint, wheel build, and install smoke tests.
