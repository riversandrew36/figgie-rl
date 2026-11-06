# Train and evaluate your first Figgie agent

The browser arena is a demonstration of four **scripted baselines**. This guide
runs actual PPO training in Python. No API keys or hosted AI services are needed.
The browser and Python use separate simulations: seeds and results do not transfer
between them, and the browser cannot load Python PPO checkpoints.

## Install and inspect

Use Python 3.10 or newer. PyTorch makes this a larger installation than the static
demo. A CPU is sufficient for the small workflow below; runtime depends on hardware.

```bash
git clone https://github.com/riversandrew36/figgie-rl.git
cd figgie-rl
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
figgie-demo --seed 17 --steps 3
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. The inspection command
prints the default environment's observation layout, action table, and reward
components. It exposes hidden metadata for debugging; those labels are not policy
inputs. The learning configuration below uses the player-quote market instead.

## The experiment

`configs/ppo_learning.yaml` runs 4,096 requested timesteps against Hunter, Banker,
and Detective in the **endogenous** market: only player quotes provide liquidity.
Goal-belief and order-flow features are enabled. PPO learns a discrete trading
policy from reward feedback. Twenty fixed validation episodes select checkpoints
by bankroll (then win rate, then rank); they are not the final test.

```bash
figgie-train --config configs/ppo_learning.yaml
figgie-eval --model-path artifacts/ppo_learning/best_model/best_model.zip \
  --config configs/ppo_learning.yaml --episodes 50 --seed 610000 \
  --benchmark --output results/learning.json
```

The small run demonstrates the pipeline. It does not promise profitable or strong
play. Training produces `best_model.zip`, final weights, metadata sidecars with
resolved configuration and seeds, and validation history under
`artifacts/ppo_learning/`. Evaluation writes per-episode results, aggregates, and
paired profit differences versus PPO. Keep the model and its matching config
together; an incompatible market changes both observations and actions.

### What to inspect

- **Observations:** private inventory, cash, visible quotes and trade flow, time,
  optional order-flow summaries, and hand-derived goal probabilities. The hidden
  goal label is not an observation. Availability flags identify empty books in
  the player-quote market.
- **Actions:** hold, trade, and quote through a discrete action table. The Python
  player-quote market uses a bounded absolute price ladder.
- **Rewards:** trading and marked inventory changes, then true settlement. Read
  `reward_breakdown` rather than equating dense rewards with final profitability.
- **Outcomes:** mean profit, uncertainty, rank, drawdown, and paired differences.
  A few wins or a small positive mean are not proof of generalization.

The initial-hand posterior is a supplied engineered feature, not an inference
mechanism learned by PPO. Comparing feature-on and feature-off runs is a useful
follow-up experiment with separate run names and matching evaluation configs.

## Change one baseline parameter

First save the benchmark above as `results/learning.json`. In
`figgie_rl/agents/styles.py`, change `DEFAULT_EDGE` from `2.0` to `3.0`; the Banker
uses this edge in its quotes. Keep the saved PPO checkpoint and YAML unchanged,
then rerun the same evaluation seeds:

```bash
figgie-eval --model-path artifacts/ppo_learning/best_model/best_model.zip \
  --config configs/ppo_learning.yaml --episodes 50 --seed 610000 \
  --benchmark --output results/wider_edge.json
```

Compare Banker's mean profit and drawdown, and PPO's results against the modified
opponents. This parameter is shared by styles, so this is a **style-policy change**,
not an isolated causal test of Banker alone. The evaluator places each candidate
in the learner seat against the configured opponent lineup; it is not a four-way
tournament among every benchmark policy. Preserve both reports and record the
code change. Undo the parameter edit before the next experiment.

## Validation, exploration, and final testing

| Purpose | Learning config seeds | Use |
| --- | --- | --- |
| Training initialization | 17, 18 | Two vector environments |
| Checkpoint validation | 600000–600019 | Selection, not final evidence |
| Exploratory benchmark | 610000–610049 | Inspect and iterate |
| Reserved final test | 620000–620199 | Only after freezing choices |

After freezing code, configuration, and checkpoint, run the reserved final test:

```bash
figgie-eval --model-path artifacts/ppo_learning/best_model/best_model.zip \
  --config configs/ppo_learning.yaml --test --benchmark \
  --output results/learning_final.json
```

Do not tune on this result. Once it informs a development choice, reserve fresh
seeds. The quickstart config's ranges are separate from the older research
configuration's reserved final range. Small sample sizes, checkpoint selection,
opponent exploitation, and the simulator's assumptions limit conclusions.

## Go further with self-play

```bash
figgie-self-play --config configs/endogenous_market.yaml \
  --iterations 6 --chunk-timesteps 100000
```

This is a substantial optional run, not part of the quickstart. Frozen learned
policies enter the opponent pool; iteration checkpoints retain metadata. Self-play
saves each iteration without validation-based checkpoint selection. Evaluate with
the matching config and reserve fresh final seeds for each frozen experiment.

See [project status](PROJECT_STATUS.md) for historical evidence and limitations.
No improved PPO performance in the newer player-quote market has been established.
