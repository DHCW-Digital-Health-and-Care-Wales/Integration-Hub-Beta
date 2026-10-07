# Copilot prompt — build the Reference Data Lookup REST API

> Paste everything in the fenced block below into a **new** Copilot chat (ideally the `modernize`/default
> agent) opened at the root of the Integration Hub repo. It describes the new microservice that the PIMS
> transformer already calls for gender / marital status / ethnic group / NHS status code translation.

```prompt
Create a new microservice `reference_data_api` under `servers/` (a FastAPI app) that serves the
PIMS -> MPI (and future flows') reference-data code lookups. The HL7 PIMS transformer already calls
this API via `transformers/hl7_pims_transformer/hl7_pims_transformer/clients/reference_data_client.py`,
so the HTTP contract below is fixed and must be matched exactly.

## Context

SBU PIMS messages arrive in HL7 v2.3.1 and must be forwarded to the eMPI in v2.5 with certain codes
translated from the PIMS source code to the code the eMPI expects. Today these translations come from
a table Integration hosts on a SQL Server (the "WRDS/WRRS lookup"). This service exposes that lookup
over HTTP so transformers do not embed the data or talk to SQL directly.

The four datasets required by the PIMS flow (see the SBU PIMS ADT Mapping Document):

| Dataset path     | eMPI target field | PIMS source           |
|------------------|-------------------|-----------------------|
| `gender`         | PID.8             | PID.8                 |
| `marital-status` | PID.16.CE.1       | PID.16.CE.1           |
| `ethnic-group`   | PID.22.CE.1       | PID.22.CE.1           |
| `nhs-status`     | PID.32            | PID.3 (NI rep) CX.2   |

## HTTP contract (MUST match the existing client)

- `GET /lookup/{dataset}/{source_code}`
  - `dataset` is one of: `gender`, `marital-status`, `ethnic-group`, `nhs-status`.
  - `source_code` is URL-encoded (e.g. the client encodes `/` as `%2F`).
  - `200 OK` with JSON body: `{"dataset": "<dataset>", "sourceCode": "<source>", "targetCode": "<code>"}`.
  - `404 Not Found` when there is no mapping for that dataset+source.
  - `400 Bad Request` for an unknown dataset name.
  - `5xx` for server/datasource errors (the client retries 429/502/503/504).
- Optional API key: if configured, require it in the `X-API-Key` request header and return `401` when
  missing/incorrect. The client sends it as `X-API-Key`.
- Also expose `GET /health` (returns `200` when the service and its datasource are ready) and the
  FastAPI OpenAPI docs.

The `targetCode` the client accepts is format-validated per dataset, so returned codes must be short,
delimiter-free tokens:
- `gender`: 1-3 alphanumerics
- `marital-status`: 1-4 alphanumerics
- `ethnic-group`: 1-4 alphanumerics
- `nhs-status`: 1-2 digits

Note: the PIMS transformer reads PID.3 CX.2 via hl7apy, which types it as numeric and **drops leading
zeros** (source `03` arrives as `3`). Key the `nhs-status` dataset on the unpadded value (`3`), or
normalise incoming `source_code` by stripping leading zeros for that dataset.

## Data source

Back the lookups with the existing SQL Server reference table(s). Add a thin repository layer with an
interface so the datasource can be swapped (SQL now; the codebase also has a Cosmos pattern in
`dashboard/dashboard/services/cosmos_store.py` if that is preferred later). Cache reads in-process with
a configurable TTL (the data changes rarely). For local development, provide a static/in-memory seed
dataset so the API runs without SQL, seeded with a few example codes for each dataset.

## Follow the repo's service conventions exactly

Model the new service on an existing FastAPI service such as `servers/rest_server` and on the patterns
in `AGENTS.md`:
- Folder layout: `servers/reference_data_api/` with inner package `reference_data_api/`
  (`application.py` / `asgi_app.py`, `app_config.py` reading all settings from `os.getenv`, routes,
  repository/datasource module), plus `tests/` with `test_*.py`.
- `pyproject.toml` with `setuptools` build backend, `requires-python = ">=3.13"`, and a `dev`
  dependency group containing `ruff`, `bandit`, `mypy`, and the test runner. Reference shared libs as
  local `uv` sources where useful (e.g. `event_logger_lib`, `health_check_lib`).
- `uv.lock` committed (`uv lock`), a `Dockerfile` using `python:3.13-slim-bookworm` + `uv`, non-root
  `appuser` (UID 5678), exposing port 8080 and running under `uvicorn`.
- A `check.sh` running: `uv run ruff check` -> `uv run bandit -r reference_data_api` ->
  `uv run mypy --ignore-missing-imports reference_data_api` -> tests.
- Config from environment only (no `.env` in production). Use `event_logger_lib` for structured
  logging (no `print`). Validate inputs; never interpolate user input into SQL (use parameterised
  queries) — this endpoint is an OWASP-relevant boundary.
- Add an Azure DevOps build pipeline under `pipeline-ado/` mirroring an existing
  `*-build.yml`, and a `README.md` documenting the endpoints and env vars.

## Env vars (suggested)

- `PORT` (default 8080), `HOST` (default 0.0.0.0)
- `REFERENCE_DATA_API_KEY` (optional; when set, enforce `X-API-Key`)
- `CACHE_TTL_SECONDS` (default 300)
- SQL connection settings consistent with the rest of the repo
  (`SQL_SERVER`, `SQL_DATABASE`, `SQL_USERNAME`, password via env/secret)
- `USE_IN_MEMORY_SEED` (default false; true for local dev without SQL)

## Tests

Use the repo's test tooling. Cover: a successful lookup per dataset, 404 for an unknown code, 400 for
an unknown dataset, 401 when an API key is required but missing/wrong, the `nhs-status` leading-zero
normalisation, and the datasource/repository layer (mocked SQL + the in-memory seed).

Finish by running `check.sh` and ensuring ruff, bandit, mypy and the tests all pass.
```
