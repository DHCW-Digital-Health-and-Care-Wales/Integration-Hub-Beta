# Code Coverage Dashboard — Plan

## Goal

Provide a code coverage dashboard, hosted in Azure DevOps, that is refreshed automatically whenever
code is merged into `main`. The dashboard must show both:

- **Detailed** coverage (per-service, per-file line/branch coverage), and
- **Graphical** coverage (overall %, trend over time across merges).

## Current State

- No coverage tooling is installed anywhere in the repo today — `pr-validation.yml` and the per-service
  `*-build.yml` pipelines run `ruff`, `bandit`, `uv audit`, `mypy` and unit tests (`unittest discover` or
  `pytest`), but none of them measure or publish coverage.
- Unit tests exist per-service under each `<service>/tests/` directory (see `code-quality-template.yml`
  and `pr-validation.yml` for the full list of ~20 services + shared libs).
- Each service is an isolated Python package with its own `pyproject.toml`/`uv.lock`/venv — there is no
  single combined test run today. This means overall coverage must be **aggregated** from N independent
  per-service coverage reports, not measured in one process.
- No coverage-related ADO pipeline tasks (`PublishCodeCoverageResults`, ReportGenerator, etc.) exist yet.

## Constraints / Decisions

1. Coverage must run on **merge to `main`** (post-merge), not on every PR — keeps PR validation fast and
   matches the ask. It will run as a new, dedicated pipeline rather than being bolted onto the 16 existing
   per-service `*-build.yml` pipelines (those only trigger for the service they build, so no single one of
   them sees "all code merged to main").
2. `coverage.py` is the tool of choice (already a transitive dependency of `bandit`/`pytest` extras in
   several services' lockfiles, PEP 8/ruff/mypy-compatible, works with both `unittest` and `pytest` runners
   used across the repo).
3. Output format: **Cobertura XML** (`coverage xml`) — natively understood by ADO's
   `PublishCodeCoverageResults@2` task and by ReportGenerator for merging.
4. Aggregation tool: **ReportGenerator** (`dotnet tool`, MIT licensed, already a common choice in ADO
   pipelines) — merges N per-service Cobertura files into one HTML/Cobertura/badges report, and supports a
   `-historydir` for a persisted trend graph across builds.
5. Dashboard = ADO **Dashboard widget(s)** (native "Code Coverage" trend widget wired to the pipeline) +
   the ReportGenerator HTML report published as a build artifact for per-file drill-down. No new external
   SaaS tool (Codecov/Coveralls) — keeps everything inside ADO as requested.

## Architecture

```mermaid
flowchart TD
    A[Merge to main] --> B[code-coverage.yml pipeline triggers]
    B --> C[Per-service job: coverage run + coverage xml]
    C --> D[Publish per-service coverage.xml as artifact]
    D --> E[Aggregate stage: ReportGenerator merges all Cobertura files]
    E --> F[PublishCodeCoverageResults@2 -- ADO build summary Coverage tab]
    E --> G[Publish merged HTML report as build artifact]
    E --> H[Update coverage-history artifact for trend]
    F --> I[ADO Dashboard: Code Coverage trend widget]
    G --> J[ADO Dashboard: Markdown/link widget -- latest detailed report]
```

## Implementation Plan

### Phase 1 — Per-service instrumentation

- Add `coverage` to the `dev` dependency group in each service's `pyproject.toml` (mirror the existing
  `ruff`/`bandit`/`mypy`/`pytest` dev-group pattern) and run `uv lock` to update `uv.lock`.
- Add a `[tool.coverage.run]` section per service: `source = ["<service_pkg>"]`, `omit = ["tests/*"]`,
  `branch = true`.
- Local dev command (documented in each service `README.md` / `check.sh`):
  ```bash
  uv run coverage run -m unittest discover tests   # or: -m pytest tests, per service's TEST_RUNNER
  uv run coverage xml -o coverage.xml
  uv run coverage report
  ```
- No behavioural change to `pr-validation.yml` or the per-service `*-build.yml` files in this phase.

### Phase 2 — New pipeline: `pipeline-ado/code-coverage.yml`

- `trigger: branches: include: [main]` (no `paths` filter — every merge to `main` refreshes the
  dashboard, matching the request literally), `pr: none`.
- Single job, same "loop over an `APPS` array" pattern already used in `pr-validation.yml`, so it stays in
  sync with the same service list (reuse/extend the shared `pipeline-ado/templates/` where sensible rather
  than duplicating logic).
- Per service: create isolated `uv venv`, `uv sync --group dev`, run
  `coverage run -m unittest discover tests` (or `pytest`, per the existing `TEST_RUNNER` flag), then
  `coverage xml -o $(Build.ArtifactStagingDirectory)/coverage-raw/<service>/coverage.xml`.
- Services without a `tests/` directory are skipped (same guard already used in `pr-validation.yml`).
- Publish `coverage-raw` as a pipeline artifact at the end of the job.

### Phase 3 — Aggregation stage

- New stage `AggregateCoverage`, depends on the per-service job.
- Install ReportGenerator: `dotnet tool install --global dotnet-reportgenerator-globaltool`.
- Run:
  ```bash
  reportgenerator \
    -reports:"coverage-raw/**/coverage.xml" \
    -targetdir:"coverage-report" \
    -reporttypes:"HtmlInline_AzurePipelines;Cobertura;Badges" \
    -historydir:"coverage-history"
  ```
- Publish `coverage-report/Cobertura.xml` via `PublishCodeCoverageResults@2` — populates the native ADO
  build "Coverage" tab (detailed, per-file, drill-into-source).
- Publish `coverage-report/` (full HTML) and `coverage-history/` as pipeline artifacts.
- Persist `coverage-history/` across runs (pipeline artifact retention is enough for trend continuity
  within ReportGenerator's own history mechanism, since each run downloads the previous run's history
  artifact before regenerating — confirm retention policy covers the merge cadence, else fall back to a
  small dedicated Azure Storage container/blob for the history JSON files).

### Phase 4 — ADO Dashboard

**Prerequisite**: `pipeline-ado/code-coverage.yml` must be registered as an actual Pipeline in Azure DevOps
and have run successfully at least once (a widget can't attach to a pipeline that doesn't exist yet in ADO,
and the Code Coverage widget only has data to plot once `PublishCodeCoverageResults@2` has run at least
once). Needs **Project/Build Administrator** permissions (or equivalent) to create pipelines and edit
dashboards.

#### 4.1 — Register the pipeline in Azure DevOps

1. Go to **Pipelines → Pipelines** in the ADO project.
2. Click **New pipeline**.
3. Choose **Azure Repos Git** (or GitHub, matching wherever `Integration-Hub-Beta` is hosted) → select the
   `Integration-Hub-Beta` repository.
4. Choose **Existing Azure Pipelines YAML file**.
5. Branch: `main`. Path: `/pipeline-ado/code-coverage.yml`.
6. Click **Continue**, review the YAML preview, then **Save** (use the dropdown next to "Run" → **Save**,
   do *not* run it yet from here if you want to name it first).
7. Rename the pipeline to something clear, e.g. **Integration Hub — Code Coverage** (Pipelines → select it
   → **⋯** → **Rename/move**, optionally into a folder like `Integration Hub/Quality`).
8. Since the YAML has `trigger: branches: include: [main]` and `pr: none`, it will **not** run
   automatically until the next merge to `main`. To validate it immediately: **Run pipeline** → branch
   `main` → **Run**.
9. Watch the run. Expected stages: `CollectCoverage` then `AggregateCoverage`. Check the build summary's
   **Tests** and **Coverage** tabs appear once it completes, and that `coverage-raw`, `coverage-report`,
   and `coverage-history` artifacts were published (**Summary** tab → **Related → N published**, or the
   **Artifacts** dropdown at the top right of the run page).
10. If the `AggregateCoverage` stage's `DownloadPipelineArtifact@2` step fails on this first run (no prior
    `coverage-history` artifact exists yet) that's expected — it's set with `continueOnError: true`, so the
    stage should still proceed and produce a fresh history file.

#### 4.2 — Create the Dashboard

1. Go to **Overview → Dashboards** in the ADO project (or the team's dashboards if using team-scoped
   dashboards).
2. Click **New Dashboard**.
3. Name: **Integration Hub — Code Quality** (or add to an existing dashboard if the team already has one
   for build health).
4. Set the team/permissions scope as appropriate (project-level so the whole team can see it), then
   **Create**.

#### 4.3 — Add the native Code Coverage trend widget

1. On the new dashboard, click **Add a widget** (+ icon).
2. Search for **"Code Coverage"** in the widget gallery and select it.
3. Configure:
   - **Project**: `Integration-Hub-Beta`'s ADO project.
   - **Build pipeline**: the pipeline created in 4.1 (e.g. "Integration Hub — Code Coverage").
   - **Branch**: `main`.
   - **Number of builds**: e.g. `10`–`20` (how many recent runs to plot in the trend line).
4. Click **Save**. This gives the **graphical** requirement — a trend line of overall coverage % across
   recent merges to `main`, refreshed automatically as the pipeline runs.
5. Resize the widget (drag the corner) to a 2×2 or 2×3 tile so the trend line is legible.

#### 4.4 — Add a Markdown widget linking to the detailed report

The native widget only shows a summary trend line; use a Markdown widget to make the **detailed** per-file
breakdown easy to find:

1. **Add a widget** → search **"Markdown"** → select it.
2. Paste content similar to:
   ```markdown
   ## Detailed Coverage Report

   - [Latest build results](<pipeline URL from step 4.1>)
   - Detailed per-file HTML report: open the latest successful run → **Artifacts** → `coverage-report` →
     download and open `index.html` (or configure a static file host / Azure Storage static website if
     you want this browsable without downloading — optional future enhancement).
   - Per-file coverage is also visible directly on each run's **Coverage** tab in the build summary.
   ```
3. Save, resize as needed.

#### 4.5 — Optional: Test Results Trend widget

Since the same pipeline publishes test results (via `coverage run -m unittest`/`pytest`, which produce
results ADO can also surface as test outcomes if a `PublishTestResults@2` task is added later):

1. **Add a widget** → search **"Test Results Trend"**.
2. Point it at the same pipeline/branch.
3. This is optional and only useful if/when test result publishing is added — coverage and test pass/fail
   are different signals, but showing them side-by-side is convenient. Skip this if you don't want to add
   `PublishTestResults@2` to the pipeline yet.

#### 4.6 — Share and verify

1. Confirm the dashboard's permissions let the whole team view it (Dashboard **⋯** → **Security**).
2. Send the dashboard link to the team (Gareth, Matt, Alex, Yoana, Alphy).
3. Merge a small PR to `main` and confirm the Code Coverage widget updates after the pipeline run
   completes (may take a minute or two after the build finishes for ADO to refresh the widget cache).

### Phase 5 — Guardrails (later, opt-in)

- Once a baseline % is established, consider a coverage floor check (`coverage report --fail-under=X`) as
  a non-blocking warning first, then promote to a blocking gate in `pr-validation.yml` if the team agrees.
- Not part of the initial rollout — avoid blocking merges before a baseline exists.

## Open Questions

- Which ADO project/team area should own the new Dashboard — reuse an existing one or create
  "Integration Hub — Code Quality"?
- Retention: how many days of `coverage-history` do we need for a meaningful trend graph, and does the
  default pipeline artifact retention policy cover that, or do we need external storage?
- Should shared_libs be included in the aggregated % (they are shared across services and already listed
  in `pr-validation.yml`'s `APPS` array) — recommendation: yes, for consistency with the existing quality
  gate list.

## Rollout Steps (summary)

1. Add `coverage` dev dependency + `[tool.coverage.run]` config to all services/shared libs (Phase 1).
2. Add `pipeline-ado/code-coverage.yml` (Phase 2) and `templates/coverage-aggregate-template.yml`
   (Phase 3), scoped to `main` only.
3. Run once manually to validate the merged Cobertura report and HTML output.
4. Create the ADO Dashboard and wire up the Code Coverage widget (Phase 4).
5. Communicate the new dashboard link to the team (Gareth, Matt, Alex, Yoana, Alphy).
6. Revisit coverage floor enforcement once a baseline is visible (Phase 5).
