# Contributing

Start with the [RL quickstart](docs/RL_QUICKSTART.md). Useful contributions include
baseline strategies, controlled RL experiments, clearer explanations, and accessible
arena interactions. Open an issue describing the question or bug before a large change.

For experiments, report code revision, configuration, market mode, opponent lineup,
training and evaluation seeds, checkpoint selection, and results with uncertainty.
Keep exploratory analysis separate from final tests. Avoid claims about real-world
trading or general Figgie strength from one simulator or opponent pool.

The packaged files in `figgie_rl/arena/` are the only browser source. The Pages build
copies them; do not edit generated `_site/` files. The browser is a separate JavaScript
simulation, not a PPO runtime. Bump `SIMULATION_VERSION` when seeded mechanics change;
share links reproduce a scenario only within a compatible simulation version.

Before a pull request:

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m pytest -q
npm ci
npm test
npx playwright install chromium
npm run test:browser
```

Include screenshots for UI changes and commands/results for experiments. Do not
commit model files, caches, generated reports, credentials, or private planning
materials. Contributions are licensed under the repository's MIT license.
