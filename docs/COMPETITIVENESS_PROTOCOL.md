# Figgie competitiveness follow-up

Previous final-test ranges 700000–700999 and 1400000–1400999 are consumed. This study uses new pilot seeds 1500000–1501099; they are exploratory and cannot be relabelled as final tests. If a pilot merits expansion, create a new study ID with new validation, exploration, and final ranges. Freeze conditions/checkpoints before opening final results.

## Staged design

**Pilot A: reward alignment.** `configs/competitiveness_pilot.yaml` holds market, lineup, PPO settings, seed, and 20,480-step budget constant across four reward/gamma treatments: historical wealth-change/gamma .99, wealth-change/gamma 1, terminal profit/gamma 1, and terminal profit with discount-consistent potential shaping/gamma .99. Run one seed and 100 validation episodes per condition. Compare deterministic and stochastic actions on the pilot exploration split. Promote at most two candidates to at least three seeds and 122,880 steps per seed. Keep Hold, Bayesian, and the four playing styles in the evaluator. Metrics: paired final profit, rank/win, quote/trade distribution, and absolute terminal-cash reconciliation. The settled return must be independent of shaping when gamma matches.

**Pilot B: teacher initialization.** Generate observations/actions from Bayesian, Hunter, Banker, Detective, and Bluffer policies from their own player views. Save teacher ID and seed per transition; the hidden goal label is excluded. Train a cross-entropy behavior-cloning policy, compare its deterministic/stochastic action behavior to each teacher, then fine-tune the best clone with the selected reward treatment. Control for environment steps and record imitation data volume, generation steps, cloning steps, and PPO steps separately. PPO-from-scratch with the same total budget is the control. Promote cloning and fine-tuning only if it beats Hold reliably and improves over the Bayesian benchmark on fresh validation deals.

**Pilot C: opponent pool.** Extend staged self-play to sample independently trained and fixed historical checkpoints as well as all four scripts. Match environment resets, rollout/update boundaries, training seeds, and step budget in a fixed-opponent control. Test against withheld mixtures and rotate seats. Keep each checkpoint hash and exact opponent sampling schedule.

**Pilot D: diversity.** Evaluate all trained policies on the same observation sets. Measure policy agreement, action entropy, quote prices by suit, executed trades, inventory, and profit. If distinct personalities are a goal, seed each policy with a different scripted teacher. Diversity itself is not a success metric unless profit and robustness are retained.

The local compute ceiling is 2,000,000 PPO environment steps total for this initial follow-up (including pilots); all runs use one CPU thread and two concurrent workers. Stop a pilot if every candidate has lower profit than Hold on its validation sample or deterministic action concentration exceeds 99% with no improvement in executed trades. Do not increase budgets after inspecting final-test data. Record source/config/dependency hashes, all seeds, checkpoint hashes, commands, CPU time, and all train/validation/exploration reports. Raw outcomes remain local.

For shaping, the terminal potential is zero and the transition term is `gamma * Phi(next) - Phi(current)`. The terminal objective is final profit. Check the identity on complete episodes before training. This preserves the discounted objective under the standard potential-shaping conditions; it does not guarantee that PPO will learn the optimal policy. Keep terminal-profit-only as an ablation.

## Promotion decision and three-seed comparison

Reward pilots produced PPO mean profits of −19.23 (wealth-change, gamma 1),
−19.23 (wealth-change, gamma .99), −69.90 (terminal profit, gamma 1), and −85.10
(potential-shaped, gamma .99) on 100 exploratory episodes. Validation profits
were below Hold for all four. Deterministic quote concentration was 96–98%; sampled
stochastic policies had much more action diversity but averaged roughly −325 chips.
Those reward variants do not advance.

Teacher cloning used five separate 3,000-transition datasets (one from each
teacher's own view), with 8 epochs and 20,480 PPO fine-tuning steps per cloned
policy. Validation action agreement ranged from 5.7% to 74.3%; exploratory profit
ranged from −27.4 to −6.6 and did not reliably beat Hold or the Bayesian baseline.
It does not advance.

The historical checkpoint-pool pilot used a 40,960-step fixed control and a
40,960-step six-checkpoint staged pool, seeded with three earlier fixed and three
earlier self-play models. The diverse-pool pilot's mean profit was −2.10 against
Hold at −7.63 on the familiar lineup (paired +5.53 ± 6.03, 95% approximate CI,
75% of episodes) and +3.46 against Hold at −2.80 on the shifted lineup (paired
+6.26 ± 5.63, 75% of episodes). It did not clearly beat Bayesian. This is the only
approach promoted, as a hypothesis worth three seeds; the pilot intervals are wide.

The main comparison in `configs/competitiveness_main.yaml` trains fixed and
historical-pool self-play PPO with seeds 49, 59, 69 for exactly 122,880 steps each.
Six 20,480-step checkpoints/stages align to four-environment 1,024-step rollouts.
Both use wealth-change rewards with gamma 1, the same Hunter/Banker/Detective
lineup, reward, observation, network, and optimizer. Self-play samples two frozen
policies without replacement from the three new staged checkpoints available so
far and six frozen historical checkpoints, leaving Hunter as the third scripted
opponent. Validation scores select all six self-play checkpoints by mean bankroll,
then outright win rate, then rank; earliest exact tie wins. Fixed-policy PPO uses
the same deterministic 200-episode validation seeds and callback rule.

Pilot environments and reward variants are exploratory only. Main validation uses
1507000–1507199, exploration 1508000–1508199, and final testing 1509000–1509999.
Both held-out lineups use the same 1,000 final seeds. The main comparisons run only
after all three seeds and all reward/pool pilots are recorded. Final action reports
include deterministic and stochastic policies on validation, with deterministic
final actions predeclared. The 2,000,000-step local budget covers 81,920 reward
pilot steps, 102,400 imitation fine-tuning steps, pilot-pool runs, and the six
122,880-step main runs. Demonstration generation and BC updates are reported
separately from PPO environment steps. Two CPU workers, one Torch/BLAS thread each.


Expanded-run execution records are stored under `results/figgie_competitiveness_20261106_expanded/`. The earlier one-seed pool sweep under the pilot directory is exploratory only.
