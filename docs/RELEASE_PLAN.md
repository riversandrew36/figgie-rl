# Figgie Learning Lab: RL-first public release

The public product is an open reinforcement-learning lab for Figgie. The browser
arena is its accessible entry point: four scripted baselines make trading and
hidden information visible. Python is the research environment for training,
evaluation, and self-play. The website must not imply that its bots are learned
policies or that it executes Python checkpoints.

## First release

- Publish the packaged HTML/CSS/JS through GitHub Pages, with no accounts or backend.
- Explain game rules and the RL loop: observations, actions, rewards, checkpoint
  selection, baseline comparisons, and self-play.
- Preserve the arena's mechanics and controls. Add seeded sharing, payout
  reconciliation, initial-hand beliefs, and factual trade highlights.
- Provide a small local PPO configuration and a tested train/evaluate workflow.
  Separate training, validation, exploratory evaluation, and reserved final tests.
- Connect the demo to documented experiments and limitations. Existing historical
  runs do not establish new player-quote PPO performance.
- Add the license, contribution guide, deployment instructions, and launch copy.
- Validate seeded execution, settlement, export, accessibility, mobile layout,
  Python packaging, and deployment at the repository-prefixed URL.

## Delivery

Create a public `riversandrew36/figgie-rl` repository after reviewing the initial
publication contents. Deploy only after lint, Python tests, wheel installation,
and JavaScript/browser checks pass. Verify the resulting Pages URL before calling
it live. Local caches, checkpoints, training logs, and private planning materials
remain excluded. GitHub authentication is required for remote creation and Pages
configuration; local implementation can proceed independently.

## Later

Guided lessons, deeper bot tutorials, browser inference, and human play follow
feedback. No new substantial training run, claim of stronger AI, multiplayer,
analytics, custom domain, or paid service is part of this release.
