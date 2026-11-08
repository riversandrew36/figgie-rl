# Initial substantive RL study — November 6, 2026

## Questions and fixed design

1. Complete the existing `ppo_simple.yaml` 120,000-step outside-book experiment,
   preserving its 200-episode validation and 1,000-episode reserved final test.
   That configuration was already specified before this study. Its training began
   before writing this comparison protocol; no final evaluation had been run.
2. In a player-quote market, compare fixed scripted-opponent PPO with staged
   self-play at equal environment-step budgets, across training seeds 7, 17, 27.
3. Evaluate both methods against familiar opponents and a changed opponent lineup.

The comparison specification is `configs/rl_study.yaml`. Each of six runs gets
122,880 environment steps (an exact multiple of 1,024-step vector rollouts).
Fixed-opponent PPO trains against Hunter, Banker, Detective. Self-play starts with
that lineup, then replaces the third opponent with a uniformly sampled earlier
frozen checkpoint for each of five later stages. Six 20,480-step stages give the
same total budget as fixed training. This is a mixed opponent-pool experiment,
not symmetric all-learned-agent self-play. Equal steps do not imply equal compute.
Both conditions use the same PPO hyperparameters and engineered goal-belief and
flow features. This study does not measure learning inference from raw inputs.

## Selection, splits, and stopping rule

- Validation: seeds 1200000–1200199, deterministic actions. Compare exactly six
  checkpoints at 20,480-step intervals per run, selecting by higher mean final
  bankroll, then higher outright win rate, then lower mean rank. An exact remaining
  tie retains the earliest checkpoint. Self-play checkpoints are validated after
  training; final-test results never select them.
- Exploration: seeds 1300000–1300199, familiar opponents only, selected models.
  These reports describe performance; this study makes no subsequent tuning changes.
- Final: seeds 1400000–1400999, both familiar (Hunter/Banker/Detective) and shifted
  (Banker/Detective/Bluffer) lineups. Each selected model is tested; no best training
  seed is chosen. Both lineups share episode seeds for comparability. Neither set
  of final results is used to change the protocol or checkpoints.
- The legacy outside-book run retains its original validation seeds 50007–50206
  and final seeds 700000–700999. Cross-market results are not directly comparable.
- A manifest records source/config hashes, package versions, commands, and seeds.
  Before any final evaluation, selected checkpoint hashes and the complete design
  are frozen in a separate file. Existing results are not overwritten on resume.

## Evaluation and reporting

Use the existing simulator and evaluator without changing game mechanics, reward,
network, or action schema. Rotate seats and action/quote tie priorities as already
implemented. Compare against Hold, Random, Market maker, Value trader, Bayesian,
Hunter, Banker, Detective, and Bluffer in the learner seat. This is not a tournament
among all policies. Scripted baseline results are model-independent and may be
computed once for each evaluation split/lineup, then reused with an explicit
provenance reference and freshly calculated paired differences for each model.

Report each training seed, not just a favorable run. Show mean profit, conditional
approximate episode-level 95% intervals, outright win rate, rank, and paired profit
differences. Also show paired self-play-minus-fixed mean-profit differences for
training seeds 7, 17, 27 and a t-based interval across those three differences
(df=2). Three seeds provide limited evidence about training variability; a pooled
3,000-episode calculation must not pretend that reused deals are independent.
Existing drawdown measures use cumulative dense rewards, not a separately sampled
bankroll curve, and will be labeled accordingly if discussed.

Keep model files, raw reports, logs, exact generated YAMLs, validation histories,
and analysis outputs locally. A local written report and learning-curve figure
will summarize results. Publishing new research claims or model files is a separate
step. No human-level or real-world trading claims follow from this simulator study.

## Reproduction

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python scripts/run_rl_study.py
```

Use the project's installed dependencies. Two subprocess workers run on CPU;
there is no cloud service or paid compute. The already-running standard experiment
must finish before its final checkpoint can be frozen. The script can be resumed
for completed stages, and refuses to silently restart partially trained runs.
