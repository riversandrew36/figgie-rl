# Project status: market integration, validation, and experiment records

Updated November 20, 2026. This is the handoff for resuming the project. Historical training results below are preserved and are not evidence of performance in the new player-quote market.


## Measured bot tiers and battles — November 20, 2026

All tier seats are scripted. Beginner uses Rookie Hunter, Rookie Detective,
and Rookie Bluffer. Their shared profile acts on 45% of turns, uses one chip
of value noise, ignores the tape, requires seven chips of expected edge
to cross, and quotes with an eight-chip spread. The profile values the
majority share at twice the standard estimate. Rookie Banker used the same
profile but its held-out interval against Banker included zero, so it was
excluded. Intermediate retains the four unprofiled styles, with Hunter,
Banker, and Detective at the default Play table.

Advanced is hidden. The picker shows it as coming soon and its battle
presets are removed, because on held-out deals every Expert scored below the
best Intermediate bot: Expert Hunt −6.06 [−9.97, −2.14], Expert Bank −7.05
[−11.28, −2.82], Expert Scout −7.70 [−11.76, −3.64], and Expert Flow −7.90
[−12.05, −3.76]. It opens automatically when `heldOut.advancedPass` becomes
true. The candidate lineup is Expert Hunt, Expert Bank, and Expert Scout,
with Expert Flow as the fourth Watch seat. Their
shared profile acts every turn, uses tape, has zero value noise, requires
two chips of expected edge, quotes a two-chip spread, and values the
majority share at 0.8 times the standard estimate. Tape weights are
0.14, 0.12, 0.18, and 0.22; inventory skews are 0.45, 0.85, 0.65, and 0.65.

The evaluation put each candidate in seat zero against default Hunter,
Banker, and Detective for 60 seconds in Players. The same seeds were used
for each subject. Development seeds were 1–400. Profiles were frozen before
opening held-out seeds 900000–900399. All numbers are chips per round, with
normal-approximation 95% intervals in brackets. Paired differences use
within-seed differences.

| Subject | Development profit | Held-out profit | Development vs Hold | Held-out vs Hold |
|---|---:|---:|---:|---:|
| Hunter | +4.11 [-1.59, +9.81] | -0.66 [-6.40, +5.08] | +7.25 [+1.03, +13.48] | +2.00 [-3.96, +7.96] |
| Banker | +2.06 [-3.00, +7.12] | -4.56 [-9.42, +0.31] | +5.20 [-0.85, +11.24] | -1.90 [-7.78, +3.99] |
| Detective | +0.56 [-4.45, +5.57] | -1.63 [-6.61, +3.36] | +3.70 [+1.09, +6.32] | +1.03 [-0.94, +3.00] |
| Bluffer | +7.19 [+1.70, +12.68] | +4.07 [-1.43, +9.58] | +10.34 [+4.79, +15.89] | +6.73 [+1.15, +12.31] |
| Rookie Hunter | -5.70 [-11.27, -0.13] | -11.84 [-17.52, -6.17] | -2.56 [-7.91, +2.80] | -9.18 [-14.28, -4.09] |
| Rookie Banker | -3.42 [-8.87, +2.04] | -8.31 [-13.85, -2.77] | -0.27 [-5.28, +4.73] | -5.65 [-10.54, -0.76] |
| Rookie Detective | -5.35 [-10.83, +0.13] | -13.64 [-19.50, -7.78] | -2.21 [-7.27, +2.86] | -10.98 [-16.21, -5.75] |
| Rookie Bluffer | +0.93 [-4.27, +6.13] | -3.74 [-9.05, +1.56] | +4.07 [-0.68, +8.82] | -1.09 [-5.69, +3.52] |
| Expert Hunt | +2.40 [-2.02, +6.83] | -1.98 [-6.17, +2.21] | +5.54 [+0.02, +11.06] | +0.68 [-4.74, +6.09] |
| Expert Bank | +2.78 [-1.92, +7.47] | -2.98 [-7.48, +1.53] | +5.92 [+0.43, +11.40] | -0.32 [-5.88, +5.25] |
| Expert Scout | +1.03 [-3.42, +5.48] | -3.63 [-7.93, +0.67] | +4.17 [-1.10, +9.44] | -0.97 [-6.19, +4.24] |
| Expert Flow | +0.59 [-3.52, +4.70] | -3.83 [-8.12, +0.46] | +3.73 [-1.18, +8.65] | -1.17 [-6.31, +3.97] |
| Hold | -3.14 [-7.85, +1.57] | -2.66 [-7.60, +2.28] | +0.00 [+0.00, +0.00] | +0.00 [+0.00, +0.00] |
| Random | -169.91 [-175.27, -164.56] | -167.69 [-172.41, -162.98] | -166.77 [-173.69, -159.85] | -165.04 [-171.56, -158.51] |

| Candidate | Development vs own style | Held-out vs own style | Development vs best Intermediate | Held-out vs best Intermediate |
|---|---:|---:|---:|---:|
| Rookie Hunter | -9.81 [-13.65, -5.97] | -11.19 [-14.88, -7.49] | -12.89 [-16.80, -8.99] | -15.92 [-20.17, -11.67] |
| Rookie Banker | -5.47 [-10.02, -0.92] | -3.75 [-8.09, +0.59] | -10.61 [-14.53, -6.69] | -12.38 [-16.45, -8.32] |
| Rookie Detective | -5.91 [-10.29, -1.53] | -12.01 [-16.79, -7.23] | -12.54 [-16.33, -8.76] | -17.71 [-22.01, -13.41] |
| Rookie Bluffer | -6.26 [-10.03, -2.50] | -7.82 [-11.86, -3.78] | -6.26 [-10.03, -2.50] | -7.82 [-11.86, -3.78] |
| Expert Hunt | -1.71 [-6.24, +2.81] | -1.33 [-5.62, +2.97] | -4.79 [-9.09, -0.50] | -6.06 [-9.97, -2.14] |
| Expert Bank | +0.72 [-2.48, +3.92] | +1.58 [-1.68, +4.84] | -4.42 [-8.85, +0.01] | -7.05 [-11.28, -2.82] |
| Expert Scout | +0.47 [-4.27, +5.21] | -2.00 [-6.70, +2.70] | -6.16 [-10.70, -1.63] | -7.70 [-11.76, -3.64] |
| Expert Flow | -6.60 [-10.99, -2.22] | -7.90 [-12.05, -3.76] | -6.60 [-10.99, -2.22] | -7.90 [-12.05, -3.76] |

Bluffer had the highest Intermediate mean on both ranges. The selected
Beginner trio improved novice-proxy profit by +4.42 [+1.90, +6.93]
on development deals and +3.65 [+1.12, +6.17] on held-out deals.
All selected Rookies were above Random and had negative paired intervals
against their matching defaults. No Expert cleared the Advanced rule.

Run `npm run rate:bots` for development only, or
`npm run rate:bots -- --check` to recompute both ranges and compare the
committed data. The check tolerates 0.0002 chips across runtimes and
checks the inline snapshot exactly. Any policy promotion requires a
separate 60-second Lab reference run. For example:

```sh
npm run rate:bots -- --held-out --policy figgie_rl/arena/policies/ppo_no_aids.js
```

The command reports Players and Lab separately and checks the optional
actor against the best Intermediate style in Lab. It does not change
the lineups. A trained actor must clear the held-out tier rule before
replacing a seat. No trained actor was promoted here. The existing PPO
actors remain available through Custom and use the Lab schedule.

## Trained-bot market and browser evaluation — November 20, 2026

Lab seats the step-1 and step-3 seed-902 actors. A round has 120 decisions, with
one turn per seat per decision and an eight-decision quote lifetime. Both
actors passed the [Python parity gate](BROWSER_POLICY_PARITY.md) on six fixed
deals each. Existing Players and Classic seed regressions match the earlier
trade logs, RNG state, and settlement.

In this browser evaluation, each subject occupied seat one in Lab at 60
seconds against Hunter, Banker, and Detective on seeds 1–200. The intervals
are normal approximations for each subject's mean, in chips per round.
The browser uses its own deals and scripted ports. These are not the Python
development results, and the intervals do not test paired differences.

| Browser seat | Mean profit | 95% interval |
|---|---:|---:|
| PPO · sees the goal | +36.95 | [30.17, 43.74] |
| PPO · no aids | −4.53 | [−6.87, −2.18] |
| Hold | −7.28 | [−13.71, −0.86] |
| Hunter | +2.56 | [−5.50, 10.62] |
| Banker | −4.37 | [−10.81, 2.07] |
| Detective | −7.05 | [−13.75, −0.35] |
| Bluffer | +2.77 | [−4.76, 10.30] |

Reproduce the embedded browser snapshot with
`npm run eval:browser-policy -- --check`. Pass `--write` to regenerate it.

## Browser research showcase — November 20, 2026

**What the AI learned** renders the archived strong-lineup ladder from
`figgie_rl/arena/rl_results.json` (2,393 bytes). Regenerate it and the
standalone HTML snapshot using `python -m scripts.export_rl_showcase`. The
training curves use seeds 901–903, and the reported profits use development
deals 5400000–5400199. Averaged across the three runs, profit fell from +46.14
with the goal shown to −5.63 with odds alone. The no-aid stage averaged −2.62,
about +4.01 above Hold and below the scripted Bayesian, Hunter, and Bluffer
baselines.

At this stage, the learned browser seats stopped at the [observation parity gate](BROWSER_POLICY_PARITY.md).
The browser expires a resting offer before Python at the requested decision
rate. The first mismatched input differs by 0.4, above the 1e-6 tolerance.
That stage produced no browser policy evaluations or confidence intervals.
Scripted browser trade logs are unchanged for the pinned seeds.

## Player front page and daily deal — November 20, 2026

The front page opens with a direct route to Play, a guided round, and the
Python training guide. The UTC daily deal uses a fixed lineup and a 60-second
round. A local reservation marks the first attempt as scored. Completed scored
rounds count toward streaks, and later attempts are practice. Result text
shares the date, profit, prediction timing, and trade edges without revealing
a hand or goal suit. Older dates remain playable.

On narrow screens, the coach uses stacked trade cards and explains the
combined majority effect using the actual payout changes. The Pages build and
wheel include the original social preview, generated by
`python -m scripts.make_og_image`. The simulation version remains 2.0.0.

## Post-round coach and lesson scoring — November 20, 2026

After a Play round settles, the coach shows the effect of reversing each
trade, a timeline of tape-adjusted goal odds, and up to three missed quotes.
The per-trade edge is the change in final bankroll when that trade is included.
Individual counterfactuals can count the same majority swing more than once,
so the reconciliation starts at the no-trade profit and shows a combined
majority effect alongside the individual edges.

| Lesson | Seed | Current pass condition |
|---|---:|---|
| Hunter | 5 | Sell Hunter a card above its value at settlement |
| Banker | 1 | Finish with positive profit |
| Detective | 19 | Lock the correct goal prediction before halftime |
| Bluffer | 4 | Sell Bluffer a card outside the goal suit |

The browser stores prediction totals, lesson progress, and up to twenty small
round summaries locally. Quote snapshots stay in memory for the coach. Seeded
trade logs and the RNG state match with snapshots enabled or disabled, and
the simulation remains at version 2.0.0.

## Teaching in the browser arena — November 20, 2026

The guided first round uses a fixed deal and scripted counterparty actions.
Your read displays starting-hand odds alongside heuristic odds that incorporate
other players’ public aggressive trades. Optional goal predictions are scored
after settlement. The tutorial prompt, odds visibility, prediction tally, and
lesson progress use local browser storage when available.

| Lesson | Seed | Tell checked in a one-minute replay | Pass condition |
|---|---:|---|---|
| Hunter | 5 | At least two early aggressive buys in its favorite suit | Predict the goal |
| Banker | 1 | Posts both bids and offers | Finish with positive profit |
| Detective | 19 | Buys after the opening fifth in a suit with positive flow | Predict the goal |
| Bluffer | 4 | At least two early aggressive buys in its decoy suit | Sell a card to Bluffer |

The teaching script ships with the standalone HTML, wheel, and Pages build.
The simulator and its scripted policies retain version 2.0.0.

## Playable browser arena — November 20, 2026

Play seats a human against three chosen scripted opponents and keeps their hands
and the goal suit private until settlement. Watch seats all four bots. The
default player market uses backed quotes, trades crossings at the resting price,
and clears the book on every trade. Classic mode supports old scenario links.
The browser accepts whole-dollar prices from $1 through $60 and includes a
four-minute round option.

Nine fixed deals and action sequences generated from the official Python market
check the browser’s books, cash, inventories, trades, and settlement. Across
seeds 1–50 at 60 seconds, the scripted bots made 617 trades, averaging 12.34 per
round with a range of 5–27. Hunter participated in 292 trades, Banker in 423,
Detective in 140, and Bluffer in 379.

## Market and reward corrections — November 8, 2026

An audit found that unscaled chip rewards let the critic's gradient dominate PPO's
shared gradient clip, about 200–580 against 0.2 for the policy. It also found
unbacked quotes blocking real trades, quotes surviving fills, and crossed quotes that
never matched. Python now defaults to `quote_rules: official`, and supports
`reward_scale`. Completed study configs pin `quote_rules: legacy` with no scaling.
Their study controllers will still refuse reruns because source hashes changed.

Interpret the November 6 PPO results below as results for the unscaled legacy setup,
not as limits on PPO in this game. An exploratory check on the official-rules market
used three training seeds (301–303), `gamma=1`, and 400 deals (seeds
9200000–9200399):

| Setup | Familiar profit | Shifted profit |
|---|---:|---:|
| PPO, raw rewards, 122,880 steps | −192.08 | −209.61 |
| PPO, reward scale 0.02, 122,880 steps | −6.01 | −5.45 |
| PPO, reward scale 0.02, 491,520 steps | −5.48 | −3.02 |
| Hold | −3.73 | −3.66 |
| Bayesian | −0.51 | −3.30 |

Scaling removes the large losses, but scaled PPO has not shown an edge over Hold or
Bayesian; the scaled PPO-minus-Hold seed intervals include zero. Bayesian's profit
against these opponents also fell from about +11 under legacy rules to about zero, so
earlier scripted-baseline edges should not be assumed under official rules. The
browser arena has not changed. This is not a held-out final test.

## Strong-lineup ladder with carried weights — November 15, 2026

`configs/strong_ladder.yaml` (`strong_ladder_20261115`) keeps Hunter, Banker, and
Detective throughout and removes one aid per step. Each step starts from the previous
step's model for the same seed. Removed aids are reported as zeros through the new
`hidden_observation_blocks` option, so the observation width never changes. Seeds
901–903 ran 204,800 steps per step, evaluated on seeds 5400000–5400199. On those
deals, Hold earned −6.63, scripted Hunter +8.40, Bluffer +7.36, and Bayesian +3.41.

| Step | Aids | Start | Final (by seed) | Trades |
|---|---|---:|---:|---:|
| 1 | goal and odds | −64.34 | +46.14 (44.0, 46.8, 47.6) | 5.5 |
| 2 | odds only | −9.40 | −5.63 (−6.3, −5.2, −5.4) | 4.0 |
| 3 | none | −5.91 | −2.62 (−0.1, −2.3, −5.4) | 7.0 |

Step 1 learned well again. Removing the shown goal dropped the policy straight back
to about Hold, and odds-only training did not recover. The skill did not carry from
knowing the goal to inferring it. Step 3 finished about +4 above Hold and traded more
than earlier no-aid runs. That is the best no-aid PPO result so far, but it is small,
on development seeds, and still below Bayesian, Hunter, and Bluffer. The next
candidate is a smoother bridge between steps 1 and 2: show the goal on a shrinking
share of deals, or blend the shown goal into the odds. A longer step 3 is also worth
trying, since it was still improving.

## Learning ladder steps 2–5 — November 15, 2026

Steps 2–5 of `learning_ladder_20261115` ran with the same seeds (901–903), 204,800
steps, and evaluation seeds 5400000–5400199. Each step trains a fresh policy; the
runner does not carry weights from one step to the next.

| Step | Goal shown | Goal odds | Lineup | Hold | Final profit (by seed) | Trades |
|---|---|---|---|---:|---:|---:|
| 1 | yes | yes | strong | −6.63 | +35.01 (44.7, 26.7, 33.6) | 4.7 |
| 2 | yes | yes | weak | −11.60 | +586.00 (583.9, 549.6, 624.5) | 23.1 |
| 3 | no | yes | weak | −11.60 | +579.35 (620.4, 529.1, 588.6) | 25.9 |
| 4 | no | no | weak | −11.60 | +596.56 (560.1, 619.5, 610.0) | 30.0 |
| 5 | no | no | strong | −6.63 | −7.17 (−11.6, −4.4, −5.5) | 1.8 |

The weak-lineup steps do not measure goal inference. Profit is about the same with
the goal shown, with only the odds, and with neither. It is reached within 40,960
steps and is larger than the $350 starting stake, so the policies are exploiting the
legacy weak/average/tough fixed quote shim noted under Current state. Step 5, the
real game against price-aware opponents with no help, stays at Hold, as in earlier
Phase 1 runs. The ladder as designed therefore does not bridge from step 1 to step 5.
Two likely changes: keep the strong lineup and remove one aid at a time (goal shown,
then odds only, then nothing), and start each step from the previous step's weights
so it works as a curriculum. Development seeds only; no held-out test.

## Learning ladder step 1 — November 15, 2026

Step 1 (`goal_shown_strong`: goal suit shown plus goal odds, strong lineup) ran with
seeds 901–903, 204,800 masked PPO steps each, evaluated on seeds 5400000–5400199.
Mean profit went from −64.34 untrained to −6.26 at the end, which is about Hold
(−6.63). Policies settled within the first 40,960 steps and made only 0.7–1.9 trades
per round. The goal-reading diagnostic earned about +79 against a similar lineup, so
PPO is not using even perfect goal information at this budget. Local outputs are in
`results/learning_ladder_20261108/step_1_goal_shown_strong/`. This run used
stable-baselines3 and sb3-contrib 2.9.2.

**Diagnosis.** A simple scripted bot that reads the goal (buy goal cards up to $20, bid
$10 on the goal, sell other suits into any bid) earned +84.41 ± 3.43 on the same
seeds, so the headroom is real. The trained policies ignored the goal input: about a
quarter of their quotes were on the goal suit, which is chance, and most were asks
at $30–60 that never fill. Observation scales were fine, and the profitable actions
were usually legal. Buying a goal card was legal on 52% of steps and selling a
non-goal card on 95%. The cause was the reward: `ev_potential` valued cards with the
initial-hand posterior even when the goal was shown. On the scripted bot's trades,
buying a goal card averaged −4.49 shaped reward and was negative 85% of the time. In
single-seed checks (seed 901), wealth-delta, settlement-only, higher-entropy, larger
reward scale, and λ = 1 variants all stayed near Hold at 122,880 steps. Shaping with
the true goal reached +48.75 at 368,640 steps.

**Fix.** On goal-shown steps, `ev_potential` now uses the shown goal for the
learner's potential. Opponents and goal-hidden steps keep the hand posterior. Rerun
as `learning_ladder_20261115` with the same seeds and budget, step 1 improved from
−64.34 untrained to +35.01 (seeds 44.7, 26.7, 33.6), with 4.7 trades per round. It
was still climbing at the end, from +22.32 at 163,840 steps. This beats Hold (−6.63)
and the scripted Hunter level seen earlier (about +6). It is still below the
scripted goal reader (+84), and these are development seeds. Steps 2–5 have not
run. Local outputs are in `results/learning_ladder_20261115/step_1_goal_shown_strong/`.

## Short mixed-lineup check and pause — November 8, 2026

Five seeds (801–805) fine-tuned Hunter copies for 491,520 steps against both lineups
with `ev_potential`. On exploratory seeds 5300000–5300399, the final policy's gain over
its imitation start was +0.62 ± 0.92 (familiar) and −3.80 ± 4.96 (shifted). This did not
meet the predeclared rule of clearly beating the copy on one lineup without clearly
losing on the other, so RL tuning is paused. `configs/learning_ladder.yaml` and
`scripts/run_learning_ladder.py` are ready if work resumes; no full ladder step has run.

## Expected-value reward comparison — November 8, 2026

`reward_mode: ev_potential` replaces last-trade marks with potential-based shaping on
expected settlement wealth from the player's initial hand. Starting from Hunter copies,
five training seeds (601–605) compared it with `wealth_delta`, using 245,760 fine-tuning
steps, validation seeds 4700000–4700399, and exploratory seeds 4800000–4800799.

| Final policy minus its own imitation start | Familiar | Shifted |
|---|---:|---:|
| `wealth_delta` | −1.98 ± 2.94 | −1.07 ± 1.10 |
| `ev_potential` | −0.15 ± 2.20 | +1.71 ± 2.17 |

Neither reward showed a reliable RL gain over imitation, because every interval includes
zero. The expected-value reward did not show the degradation trend of the control and
is the better candidate for longer runs, but the study does not establish that it is
superior. Phase 1 remains incomplete and no held-out test was run.

## Teacher warm-start pilot — November 8, 2026

Masked PPO actors and critics were pretrained on 2,000 teacher rounds, then fine-tuned
for 245,760 steps with reduced learning rate, clip range, and entropy. Training seeds
501–503, validation seeds 4300000–4300199, and exploratory seeds 4400000–4400399 were
used; `configs/warm_start_pilot.yaml` and `scripts/run_warm_start_pilot.py` define the
run. Imitation agreement on held-out teacher rounds was 88–91% for Hunter and 66–67%
for Bluffer.

Before any RL, the Hunter copy beat Hold on both lineups (+4.68 ± 0.65 familiar,
+6.91 ± 3.19 shifted) and beat Bayesian on familiar (+1.23 ± 0.65). It trailed its
teacher on familiar by 1.67 ± 0.65. PPO fine-tuning did not improve on the copies:
final Hunter profit moved from −0.12 to −1.14 on familiar and from +0.38 to −1.07 on
shifted. The edge shown here comes from imitating scripted knowledge, and is not
evidence that RL learned to trade. Phase 1 remains incomplete and no held-out test
was run.

## Phase 1 development pilot — November 8, 2026

The pilot compared flat and structured masked PPO, with and without per-opponent
public history (`include_player_history_features`). It used training seeds 401–403,
491,520 steps per run, validation seeds 4000000–4000199, and exploratory seeds
4100000–4100399. Local outputs are in `results/phase1_pilot_*_20261108/`; summarize
them with `scripts/report_phase1.py`.

No condition beat Hold and Bayesian. Across both lineups, mean profit stayed between
−3.0 and +1.9 chips, and the new history inputs did not help at this budget. Most
learned actions were quotes, usually asks, with only 0.1–5.2 trades per round on the
familiar lineup. Phase 1's five-seed held-out test was not run, so no test seeds were
spent.

On separate seeds 4200000–4200799, a diagnostic that cheats by reading the goal suit
earned up to about +79 (familiar) and +82 (shifted) with a $16 price cap. This is an
upper reference, not a playable strategy. Scripted Hunter earned +6.29 and +7.25,
Bluffer +5.47 and +7.18, and Bayesian +1.28 and 0.00. Future exit criteria should
include Hunter and Bluffer, which are stronger baselines than Bayesian here.

## Independent matched confirmation completed — November 6, 2026

Fresh seeds 83, 97, 109 and matched stage resets/checkpoint timing were evaluated
on both final lineups (500 unseen shared deals each). See [confirmation results](CONFIRMATION_RESULTS.md)
and the local report `results/figgie_confirmation_20261106/REPORT.md`.

Fixed/pool profits: familiar −40.52/−0.94; shifted −38.05/−1.64 chips per round.
Pool results are more consistent but do not reliably beat Hold, and trail Bayesian.
The matched three-seed method-difference intervals include zero. Deterministic
pool policies remain dominated by selling particular suits. Final seeds
1800000–1800499 are consumed. No post-test tuning or publication occurred.

## Competitiveness follow-up wrap-up — November 6, 2026

All four requested approaches were implemented and piloted: reward alignment,
baseline ladder evaluation, five teacher-specific BC/PPO policies, and a diverse
historical checkpoint pool. The reward and imitation pilots did not reliably beat
Hold. The historical pool was promising on one exploratory seed (−2.10 familiar,
+3.46 shifted), and advanced to six matched-budget training runs.

All six 122,880-step main runs finished. Remaining checkpoint selection and final
evaluation were stopped at the user's request to finish up now. Main final seeds
1509000–1509999 were not opened. The main results do not yet support a final
competitiveness claim. Seed 49 was also used in the pilot, so an independent
confirmation should add a fresh third seed or exclude that development seed.

Completed local report: `results/figgie_competitiveness_20261106_pilot/REPORT.md`.
Pilot figures, raw per-episode evaluations, configs, models, and source hashes are
saved locally. No website, model, or result publication was performed.

## Substantive RL study completed — November 6, 2026

The full standard v2 run, three fixed-opponent and three six-stage self-play runs,
and their final held-out evaluations are complete. See [the study summary](RL_STUDY_RESULTS.md)
and the local generated report `results/rl_study_20261106/REPORT.md`.

Player-quote mean profits across three training seeds were −96.05 (fixed) and
−113.27 (self-play) against familiar opponents; −109.20 and −122.63 against the
changed lineup. The study does not resolve a self-play advantage. Deterministic
policies showed near-constant quote behavior. A post-hoc diagnostic identified a
ranking mismatch between discounted marked-wealth rewards and final cash, which
is a priority for a future controlled study rather than a post-test adjustment.

Final seeds 700000–700999 and 1400000–1400999 have now been examined. Preserve
these reports; reserve fresh test ranges for any future tuning informed by them.
Models and raw reports remain local. Public website claims have not been changed.

## Action interface comparison completed — November 6, 2026

Implemented and tested optional action feasibility masks and a policy with
conditional action, suit, and price heads. Both retain the existing market
execution and 105-action mapping. The corrected four-condition comparison used
three seeds and 20,480 PPO steps per seed. Masking reduced infeasible pre-step
choices to zero; average profit effects were positive but inconclusive. The
structured policy did not improve profit at this budget. All conditions remained
below Hold and Bayesian in both lineups. See the local
[action interface report](../results/action_interfaces_20261106_v2/REPORT.md).

An earlier partial pilot used an incorrect high-price rung lookup and was excluded
from results. The corrected implementation has a regression test for the $60 bid
against $59/$60 cash, plus bit-for-bit seeded comparisons in both market modes.
The action study's final-seed ranges are exploratory development data, not an
untouched confirmatory final test. The new MaskablePPO models require the supplied
mask-aware evaluator/loader. Existing browser bots remain scripted and are unchanged.

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
final test were subsequently completed in the substantive study above. Generated models and reports stay local.

## Current state

- Arena packaging, JSON/CSV benchmark exports, PPO metadata sidecars, and CI are implemented.
- The environment has two market modes: the historical outside-book (`exogenous`) mode and player-quote (`endogenous`) mode. The latter has no forced fills or random outside order flow. It uses a 12-rung absolute quote ladder from $1 to $60 and requires a real player quote for a trade.
- Hunter, banker, detective, and bluffer styles quote according to their hand/tape estimates. Reservation market makers provide another price-aware opponent. Legacy weak/average/tough policies still use a fixed quote shim and can be exploited in the new market.
- Frozen self-play now handles both market modes, restores feature settings from checkpoint metadata, and reconstructs bounded prices plus availability flags for empty books. It honors explicit feature flags and the configured opponent lineup, replacing the third scripted opponent with a frozen checkpoint after iteration zero. Without a configured lineup, endogenous self-play starts with two reservation market makers and a Bayesian trader.
- Every self-play checkpoint and final model now has a metadata sidecar. Self-play saves each iteration without bankroll selection; `checkpoint_selection` is null.
- Standard PPO and endogenous configs now validate on 200 episodes every 20,000 training timesteps. Validation seeds are 50007–50206. The smoke config remains intentionally small. The self-play CLI does not use its YAML validation settings.
- The configs reserve final-test seeds 700000–700999. Training rejects validation/test overlap and never executes the final test. The evaluator's `--test` option selects the reserved range, rejects seed/count overrides, and labels the report as a test result.
- The standard config now writes to `artifacts/ppo_goal_belief_v2/` to preserve the earlier goal-belief checkpoint. The full v2 run and reserved final test are now complete; see the study summary above.

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

The following reproduces the completed standard final test. Future experiments informed by its results need fresh test ranges:

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
