# Browser policy parity gate

Both seed-902 MaskablePPO actors are available in the separate Lab market.
This is the median seed for step 3, and its carried step-1 checkpoint supplies
the goal-shown comparison. No Python runtime or checkpoint is required to play.

## What Lab changed

The earlier probe found a 0.4 observation mismatch at learner decisions 4–7.
The ordinary Players market expired the $8 offer after eight 250 ms ticks.
Python still had it because its quote age advances once per learner decision.
Lab now runs 120 decisions per round. At 60 seconds, a decision takes 500 ms
and a quote expires after eight decisions (four seconds). Lab draws an action
rotation and a separate quote tie priority once from the browser's seeded RNG.
The learned actor observes the state before ageing, as in Python, and its
chosen action executes at its place in the rotation after ageing. Each human
turn consumes at most one queued action. Players and Classic are unchanged.

## Verification

The checked-in fixture replays six fixed Python deals with rotations covering
all four start seats. For each actor, it checks 96 observations around quote
expiry, crossings, empty books, and the last two decisions. The forecast
blocks are zeroed for the no-aids actor. Goal-oracle values are supplied only
to the goal-shown actor. The actor's action selection uses the same observable
feasibility mask as Python. The comparison checks:

| Quantity | Maximum absolute difference | Limit |
|---|---:|---:|
| Observation | 4.93e-9 | 1e-6 |
| Raw logit | 1.77e-6 | 1e-4 |

Every mask and masked argmax matched. This gate compares the actor on the same
market states. Browser deals, RNG, and scripted opponent ports are separate
from Python's. Browser performance is reported separately.

```sh
# Requires the local study checkpoints and summaries.
python -m scripts.export_browser_policy
npm test
npm run eval:browser-policy -- --check
```

Only 201,869 bytes for the goal-shown actor and 201,954 bytes for the no-aids
actor ship. Each file loads when its seat is selected. The parity fixture is
293,388 bytes and is used by Node tests, outside the public Pages payload.
