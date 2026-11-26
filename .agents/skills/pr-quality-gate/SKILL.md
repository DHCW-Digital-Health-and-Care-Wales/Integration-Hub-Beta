---
name: pr-quality-gate
description: >-
  Run the full Azure DevOps CI-equivalent code quality, security, type-checking,
  and test gates before committing or opening a pull request in Integration-Hub-Beta
  (and companion Integration-Hub-Terraform changes), then create PRs following team
  conventions. Use whenever preparing commits, validating changes before a PR, or
  creating/updating pull requests.
---

# PR Quality Gate — NHS Wales Integration Hub

Local `check.sh` scripts in this repo can lag behind Azure DevOps CI (for example,
ADO runs `mypy` on **both** `<pkg>/` and `tests/`, and runs `uv audit --locked` and
`bandit --severity-level medium`). Use this skill before committing or opening any PR
so CI failures are caught locally first.

## 1. Identify Affected Components

Check `git status` and `git diff --name-only` to list every modified service,
shared library, dashboard, JS file, or Terraform file.

- If `shared_libs/*` changed, validate the modified library **and** downstream
  services that depend on it.
- If `pyproject.toml` changed in any app, run `uv lock` first — CI runs
  `uv sync --locked` and fails on stale lockfiles.

## 2. Run CI-Equivalent Checks

Run the bundled helper script for each modified Python app/library directory:

```bash
bash .agents/skills/pr-quality-gate/scripts/check-app.sh <app_dir>
```

Examples:
- `bash .agents/skills/pr-quality-gate/scripts/check-app.sh dashboard`
- `bash .agents/skills/pr-quality-gate/scripts/check-app.sh servers/hl7_server`
- `bash .agents/skills/pr-quality-gate/scripts/check-app.sh shared_libs/message_bus_lib`

The script mirrors `pipeline-ado/pr-validation.yml` and
`pipeline-ado/templates/code-quality-template.yml`:

1. **Ruff:** `uv run ruff check .`
2. **Bandit:** `uv run bandit -r <pkg> tests --severity-level medium`
3. **Dependency audit:** `uv audit --locked --ignore GHSA-5239-wwwm-4pmq`
4. **MyPy (package + tests):** `uv run mypy <pkg> tests --ignore-missing-imports`
5. **Unit tests:** `pytest tests -v` for `dashboard` and `mock_receivers/http_mock_receiver`;
   `python -m unittest discover tests -v` for all other apps and shared libs
6. **JavaScript syntax (if `.js` files exist):** `node --check` on modified `.js` files

### Companion Terraform Checks (if `Integration-Hub-Terraform` was modified)

```bash
cd ../Integration-Hub-Terraform
terraform fmt -check <modified_tf_files>
uv run --python 3.13 python -m unittest discover -s scripts/generate-flows/tests
```

## 3. Git & Pull Request Hygiene

Before committing and opening a PR:

1. **Sync base branch:** Run `git fetch origin` and check whether `origin/main`
   has moved (also confirm an existing PR wasn't already merged before pushing to
   its branch).
2. **Stage only intended files:** Never commit `.env` files, secrets, or unrelated
   untracked notes/review docs.
3. **Branch naming:** Use `fix/<short-slug>`, `feat/<short-slug>`, or
   `INTHUB-<ticket>-<description>` branched from `origin/main`.
4. **Commit trailer:** Include:
   ```text
   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
   ```
5. **Reviewers:** Request the team's usual reviewers (`AlexJRichards`,
   `MattS1974`, `yoanaCh`, `mingletron` — excluding the PR author from
   `gh api user --jq '.login'`).
6. **PR description:** Include summary, root cause, detailed per-file changes,
   backwards-compatibility/blast-radius notes, verification commands + results,
   and cross-links to any companion `Integration-Hub-Beta` /
   `Integration-Hub-Terraform` PR.
