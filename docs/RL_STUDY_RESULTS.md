# Initial substantive RL study — November 6, 2026

Completed the original outside-book PPO run plus a matched-budget fixed-opponent
versus staged-self-play comparison in the player-quote market. Total training:
858,112 actual environment steps. The comparison used seeds 7, 17, and 27 per
method, six validation checkpoints per run, and 1,000 held-out episode seeds for
each final opponent lineup. All models were frozen before reading final results.

## Results

Mean final profit in chips, averaged over the three training seeds:

| Opponents | Fixed-opponent PPO | Staged self-play |
|---|---:|---:|
| Hunter / Banker / Detective | −96.05 | −113.27 |
| Banker / Detective / Bluffer | −109.20 | −122.63 |

Training-seed variability is large. The paired seed-level intervals include zero
for self-play-minus-fixed, so this study does not resolve a self-play advantage.
On familiar opponents, Hold averaged −5.41 and the Bayesian baseline +12.37.
The separate single-seed outside-book PPO run averaged −5.25 ± 2.41 chips
(approximate episode-level 95% interval); its market and opponents differ.

The selected deterministic policies chose one particular suit/price quote on at
least 96% of steps in a 50-deal exploratory diagnostic. They did not demonstrate
broad adaptive trading on that sample. The evaluation includes the supplied
Bayesian hand-posterior feature; it does not establish learned inference from raw
hands.

## Reward alignment finding

Terminal settlement reconciles correctly: undiscounted rewards equal final cash
minus post-ante initial marked wealth. However, with `gamma=0.99`, early paper
inventory gains receive more weight than late settlement losses. The discounted
objective can rank a heavily losing quote policy above a less costly one.
For example, fixed seed 17 averaged +83.04 discounted reward and −146.73 final
profit over 50 exploratory deals; fixed seed 7 averaged +32.70 discounted reward
and −1.64 final profit. These diagnostic outcomes are separate from final tests.

This is a concrete reward-objective concern consistent with the observed behavior,
not proof that it alone caused the training outcomes. A follow-up should compare
an undiscounted finite-horizon objective or discount-consistent potential shaping,
using fresh validation/test ranges and a fixed budget. No such change or retraining
was made after reading these final tests.

## Local artifacts and reproduction

Generated models and reports remain local and are excluded from Git. The complete
report is `results/rl_study_20261106/REPORT.md`, alongside raw per-episode reports,
source/configuration hashes, a frozen model-selection manifest, dependency lock,
validation histories, action traces, CSV/JSON summaries, and PNG/SVG figures.
The exact design is in [the study protocol](RL_STUDY_PROTOCOL.md).

To reproduce the original experiment in a fresh checkout/environment:

```bash
python -m pip install -e ".[dev]" matplotlib
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
python -m figgie_rl.train.train_ppo --config configs/ppo_simple.yaml
python scripts/run_rl_study.py
python scripts/diagnose_rl_study.py
python scripts/analyze_rl_study.py
```

Completed stages can be reused when source/config hashes match. The controller
refuses to silently overwrite partial training. Use a new study ID and new final
seeds for future experiments informed by these findings.

Consumed final-test ranges: 700000–700999 for the legacy run, and
1400000–1400999 for both player-quote lineups. They must not be described as
untouched test data in future work. No new public performance claim or trained
browser agent was published as part of running this study.
