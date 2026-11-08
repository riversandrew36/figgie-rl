# Feasibility masks and structured trading decisions

`ActionInterface(SimpleFiggieEnv(...))` exposes `action_masks()` for MaskablePPO.
True means feasible at the current observed decision state. Hold is always allowed.
Immediate buys need another player's visible ask and sufficient own cash; sells
need a visible bid and own inventory. Quote bids require current cash backing and
quote asks require current inventory. Current backing is per quote, not a reservation
across all open quotes. All quote levels, including expensive ones, remain available
when backed. Passive quotes remain possible on an empty book. The mask does not
inspect counterparties' private cards/cash or the hidden goal. It cannot guarantee
execution after earlier actors change the book. The engine still handles those
races and retains its exact rules, action indices, and settlement.

`StructuredMaskablePolicy` models kind, suit conditioned on kind, and price conditioned
on quote side/suit. It computes their joint probabilities over the existing 105
unique actions. Hold and immediate trades have no meaningless suit/price aliases.
The feasibility mask is applied to the joint distribution, followed by renormalization.
This is a factored scoring policy over the legacy action IDs, not an independent
MultiDiscrete action tuple. Initial branch priors make all leaves equiprobable.
The feature/value MLPs remain the same; the structured output heads have a modest
parameter-count difference, reported by the pilot.

## Bounded implementation comparison

`configs/action_interfaces.yaml` predeclares a 2×2 ablation: flat vs structured,
masking off vs on. Each condition uses fresh seeds 211, 223, 227, two 10,240-step
stages, the same stage reset seeds, opponents, reward, and optimization settings.
Total new training: 245,760 environment steps; two single-thread CPU workers.
Validation seeds 3000000–3000039 choose between two post-update checkpoints by
mean profit, then outright win rate, then rank; earliest exact tie wins. Freeze
selected weights before exploratory benchmarking. Benchmark seeds 3100000–3100099
against both familiar and shifted lineups. Hold and Bayesian use the same deals.
These are development results, not a new untouched final-test claim. No tuning
or longer training follows automatically from the exploratory outcomes.

All four cases use MaskablePPO; unmasked controls explicitly set `use_masking=False`.
Masks must also be passed during evaluation, as done by the new runner. Generic
`figgie-eval` and the old frozen-opponent adapter are for the original PPO checkpoints;
do not use them to evaluate masked policies. New checkpoints use MaskablePPO.load
with their recorded interface metadata and an ActionInterface-wrapped environment.
Existing checkpoints and their CLIs retain their behavior.

Run `figgie-action-study --config configs/action_interfaces.yaml` from a source
checkout after installation. Logs, validation histories, selected weights, raw
exploratory episodes, feasibility diagnostics, parameter counts, and hashes stay
under `results/action_interfaces_20261106/`. `scripts/report_action_interfaces.py`
generates the local report and charts. No website publication is part of this work.
