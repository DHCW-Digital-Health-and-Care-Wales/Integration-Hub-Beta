# Copilot Instructions — NHS Wales Integration Hub

This file is automatically loaded by GitHub Copilot CLI and coding agents.
It provides the context needed to work effectively in this repository.

---

## Project Overview

The **NHS Wales Integration Hub** is a cloud-native microservices platform built by
**DHCW (Digital Health and Care Wales)** to route HL7 clinical messages between disparate
healthcare systems. It runs on **Azure Container Apps** backed by **Azure Service Bus**.

Brand: DHCW colours — NHS Wales Blue `#325083`, DHCW Blue `#12A3C9`, DHCW Navy `#1B294A`,
DHCW Yellow `#F8CA4D`. Font: Rubik. Always use these when writing UI code.

---

## Repository Structure

```
Integration-Hub-Beta/
├── ca-certs/                    # Corporate CA certificates (injected into containers)
├── shared_libs/                 # Internal Python libraries (installed as local uv sources)
│   ├── event_logger_lib/        # Azure Monitor / App Insights logging
│   ├── field_utils_lib/         # HL7 field parsing helpers
│   ├── health_check_lib/        # Standardised health check endpoints
│   ├── hl7_validation/          # HL7 schema validation
│   ├── message_bus_lib/         # Azure Service Bus client wrapper
│   ├── metric_sender_lib/       # Azure Monitor metrics
│   ├── processor_manager_lib/   # Message processing loop + error handling
│   └── transformer_base_lib/    # Base classes for transformer services
├── local/                       # Docker Compose local dev environment
├── pipeline-ado/                # Azure DevOps CI/CD pipelines
├── dashboard/                   # NOC monitoring dashboard (Flask) ← NEW
├── buswatch/                    # Service Bus queue inspector (FastAPI)
├── hl7_server/                  # Generic MLLP HL7 receiver
├── hl7_phw_transformer/         # PHW → MPI transformer
├── hl7_chemo_transformer/       # ChemoCare → MPI transformer
├── hl7_pims_transformer/        # PIMS → MPI transformer
├── hl7_sender/                  # HL7 message delivery to MPI
├── hl7_subscription_sender/     # Subscription-based outbound sender
├── hl7_mock_receiver/           # Mock MPI target for local testing
├── message_store_service/       # Persists messages to Azure SQL
├── message_replay_job/          # Replays stored messages from SQL
└── network_test_app/            # Network/firewall connectivity tester
```

---

## Integration Flows

There are five HL7 message flows. Each has a pre-transform queue, optional transformer
container, post-transform queue, sender, and destination.

| Flow | Source Port | Pre-queue | Transformer | Post-queue | Destination |
|------|-------------|-----------|-------------|------------|-------------|
| PHW → MPI | 2575 | `pre-phw-transform` | `hl7_phw_transformer` | `post-phw-transform` | MPI |
| Paris → MPI | 2577 | `pre-paris-transform` | *(none)* | `post-paris-transform` | MPI |
| ChemoCare → MPI | 2578 | `pre-chemo-transform` | `hl7_chemo_transformer` | `post-chemo-transform` | MPI |
| PIMS → MPI | 2579 | `pre-pims-transform` | `hl7_pims_transformer` | `post-pims-transform` | MPI |
| MPI Outbound | — | `mpi-outbound` | *(none)* | *(none)* | Downstream systems |

Queue names are overridable via environment variables (e.g. `QUEUE_PHW_PRE`).
Alert thresholds: `QUEUE_WARNING_THRESHOLD=10`, `QUEUE_CRITICAL_THRESHOLD=50`, `DLQ_WARNING_THRESHOLD=1`.

---

## Service Structure Convention

Every service follows this layout — **always match this when adding or modifying services**:

```
service_name/
├── Dockerfile                   # python:3.13-slim-bookworm + uv, non-root appuser (UID 5678)
├── .dockerignore
├── pyproject.toml               # setuptools build, ruff + bandit + mypy + pytest in [dev]
├── uv.lock                      # Committed lockfile — always run `uv lock` after dep changes
├── check.sh                     # Local quality gate: ruff → bandit → mypy → pytest
├── README.md
├── service_name/                # Inner Python package (same name as folder)
│   ├── __init__.py
│   ├── app.py / application.py  # Entry point
│   └── config.py                # Reads env vars via os.getenv — no dotenv in production
└── tests/
    ├── __init__.py
    └── test_*.py
```

---

## Dockerfile Pattern

All services use this pattern — **do not deviate**:

```dockerfile
FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Services that need corporate certs also add:
# COPY --from=ca-certs ./*.crt /usr/local/share/ca-certificates/
# RUN update-ca-certificates
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv --native-tls sync --locked --no-install-project --no-dev
COPY service_name/ /app/service_name/
RUN uv --native-tls sync --locked --no-dev
ENV PATH="/app/.venv/bin:$PATH"
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser
```

Web services expose port **8080** and use `gunicorn` (Flask) or `uvicorn` (FastAPI).
Background workers use `CMD ["python", "-m", "service_name.application"]`.

---

## pyproject.toml Pattern

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "service-name"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [...]

[dependency-groups]
dev = [
  "ruff==0.14.9",
  "bandit==1.9.2",
  "mypy==1.18.2",
  "pytest>=8.3.0",
]

[tool.ruff]
line-length = 120

[tool.ruff.lint]
select = ["E","F","W","A","PLC","PLE","PLW","I"]

[tool.bandit.assert_used]
skips = ["*/test_*.py", "*/*_test.py"]
```

Shared libs are referenced as local uv sources:
```toml
[tool.uv.sources]
message-bus-lib = { path = "../shared_libs/message_bus_lib" }
```

---

## check.sh Pattern

Every service has a `check.sh` for local quality checks — run before committing:

```bash
#!/bin/bash
set -e
uv run ruff check
uv run bandit -r service_name/ tests/
uv run mypy --ignore-missing-imports service_name/
uv run pytest
```

Run it with: `bash check.sh`

---

## Dashboard (`dashboard/`)

The NOC monitoring dashboard is a **Flask 3** web app. Run locally with:

```bash
cd dashboard
uv run flask --app dashboard.app run
# or with gunicorn:
uv run gunicorn dashboard.app:app --bind 0.0.0.0:8080
```

Key files:
- `dashboard/app.py` — Flask routes, 30s in-memory cache for `/api/status`
- `dashboard/config.py` — All env vars (Azure creds, queue names, thresholds)
- `dashboard/services/service_bus.py` — Queue depth via Azure Management API
- `dashboard/services/azure_monitor.py` — Exceptions + message counts from Log Analytics
- `dashboard/services/flows.py` — Flow definitions and health calculation
- `dashboard/services/container_apps.py` — Container Apps metrics

Required environment variables (see `config.py` for full list):
```
AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP
AZURE_SERVICE_BUS_NAMESPACE
AZURE_LOG_ANALYTICS_WORKSPACE_ID
FLASK_SECRET_KEY
```

The app degrades gracefully — all pages return data (or empty state) when Azure is not configured.

---

## Development Conventions

- **Package manager**: `uv` — always use `uv add`, `uv run`, `uv sync`, never `pip`
- **Python version**: 3.13 (except dashboard which uses 3.14 locally via `.python-version`)
- **Imports**: absolute only — `from dashboard.services.flows import ...`, never relative
- **Config**: read from `os.getenv()` only — no `.env` files in production containers
- **Logging**: standard `logging` module, structured log lines via `event_logger_lib`
- **Branching**: `INTHUB-<ticket>-<description>` (e.g. `INTHUB-586056-Dashboard`)
- **Commits**: include `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer
- **Tests**: pytest, placed in `tests/`, named `test_*.py`
- **No secrets in code** — all credentials via environment variables

---

## Local Development

Docker Compose profiles in `local/` map to flows:
- `phw-to-mpi` — PHW server, transformer, sender
- `paris-to-mpi` — Paris server, sender (no transformer)
- `chemo-to-mpi` — Chemo server, transformer, sender
- `pims-to-mpi` — PIMS server, transformer, sender

Start a profile: `docker compose --profile phw-to-mpi up`

The Service Bus emulator config is in `local/ServiceBusEmulatorConfig.json`.
Each service has a corresponding `.env` file in `local/` (e.g. `phw-hl7-transformer.env`).
