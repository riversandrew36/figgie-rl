# GitHub Pages

The source is the installed arena's HTML, CSS, and JavaScript. No Python training
server, framework build, account system, or paid service runs in production.

## First setup

1. Authenticate the GitHub CLI (`gh auth login`) if necessary.
2. Create the public `riversandrew36/figgie-rl` repository from the reviewed local
   Git checkout, with `main` as the default branch. Push the initial commit.
3. Under repository Settings → Pages, select **GitHub Actions** as the build source.
   The API equivalent is `gh api --method POST repos/riversandrew36/figgie-rl/pages -f build_type=workflow`.
4. Run the **Pages** workflow manually if the first push preceded Pages setup.
5. Wait for all validation jobs and deployment to pass, then verify the URL printed
   by the deployment job in a fresh browser session.

Expected address: `https://riversandrew36.github.io/figgie-rl/`. Treat this as a planned
address until the workflow and public browser checks confirm it is live. Set the
repository homepage to this URL only after verification.

## Pipeline and local preview

The reusable CI workflow runs lint, Python tests, wheel install smoke checks,
JavaScript deterministic tests, and Chromium end-to-end tests. Pages calls the same
validation workflow, so publishing does not race a separate CI result. Pull requests
validate but cannot deploy. Pushes to `main` and manual dispatch validate then deploy.
Only the deployment job gets `pages: write` and `id-token: write`.

```bash
python3 scripts/build_pages.py
python3 -m http.server 8765 --directory _site --bind 127.0.0.1
```

Visit `http://127.0.0.1:8765/figgie-rl/`. Staging copies exactly three files to
`_site/figgie-rl/` (HTML renamed to `index.html`). The workflow uploads that inner
directory as the Pages root. Relative asset links work at the repository prefix.
Python checkpoints, docs, and local artifacts are not in the deployed payload;
source and research links point to the public repository.

## Updates and rollback

Push changes through a pull request, inspect validation, then merge into `main`.
After deployment, check loading, a completed round, sharing, and logs. No analytics
or monitoring service is installed; GitHub Actions reports build/deploy failures.
To roll back, revert the faulty commit and push the revert to `main`. The same checks
and deployment run again. Never rewrite public history to roll back a release.
