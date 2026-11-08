# Independent confirmation completed — November 6, 2026

Three fresh training seeds (83, 97, 109) were trained with identical six-stage resets,
optimizer continuity, and post-update checkpoint timing for fixed and historical-pool
opponents. New training total: 737,280 steps. Models were frozen before final tests.
Each final lineup used 500 shared unseen deals. All 93 regression tests and Ruff passed.

| Lineup | Fixed mean profit | Pool mean profit | Pool minus Hold | Pool minus Bayesian |
|---|---:|---:|---:|---:|
| familiar | -40.52 | -0.94 | +1.86 ± 4.64 | -11.88 ± 4.64 |
| shifted | -38.05 | -1.64 | +0.64 ± 7.61 | -9.30 ± 7.61 |

Intervals are t95 across three training-seed means, conditional on common final deals.
Pool training is descriptively more stable, but neither its difference from fixed
training nor its improvement over Hold is resolved by this small seed sample. It
trails Bayesian on both lineups. Deterministic fixed policies remain nearly constant;
pool policies mostly liquidate particular suits. Sampled policies lose substantially.

The complete local report is `results/figgie_confirmation_20261106/REPORT.md`, with
CSV/JSON results, PNG/SVG charts, raw validation/exploration/final episodes, sampling
schedules, source hashes, selected checkpoint hashes, and saved model sidecars.
Final seeds 1800000–1800499 are now consumed. Future tuning needs fresh test data.
All outputs remain local. No website or model publication was performed.
