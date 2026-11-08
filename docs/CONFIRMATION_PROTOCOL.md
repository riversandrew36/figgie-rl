# Independent matched confirmation

New training seeds 83, 97, 109; validation 1600000–1600099; diagnostic exploration
1700000–1700099; final 1800000–1800499. No preceding study used these ranges.

Two arms: fixed Hunter/Banker/Detective, or Hunter plus two uniformly sampled
historical learned policies without replacement. Historical policies include six
preexisting models and the current learner's earlier stages. Both arms train for
six 20,480-step stages (122,880 steps total), reset environments with identical
seed formulas at every boundary, save after optimization at identical boundaries,
and retain the PPO optimizer across stages. Preserve global Torch/NumPy RNG around
frozen-opponent loading so that loading does not reseed the learner.

Wealth-change reward and PPO gamma=1, same 47 observations, 105 actions, engineered
belief/flow features, policy and optimizer settings. No reward normalization.
Validation compares all six checkpoints using mean final bankroll, then outright
wins, then lower rank; earliest exact tie wins. Every seed is reported. Freeze all
six selected model hashes before any final evaluation. Deterministic final actions.
Evaluate stochastic and deterministic behavior on validation only.

Final lineups: Hunter/Banker/Detective and Banker/Detective/Bluffer. Both use the
same 500 final deals. Scripted baselines occupy the learner seat; reuse identical
baseline episodes across models, recalculating paired differences for each model.
Report paired differences against Hold and Bayesian and pool-minus-fixed by
training seed, with t95 across three seed means (df=2), conditional on the shared
deals. Do not pool repeated deals as independent trials. This is a simulator claim.

Budget: 737,280 training steps, two single-thread CPU workers, 500 final episodes
per model/lineup plus cached baselines. Maximum execution window two hours. No
post-test tuning, paid compute, publication, or model upload. Preserve all artifacts.
