# Integration Hub Dashboard

NOC monitoring dashboard for the NHS Wales Integration Hub.

Provides real-time visibility of all HL7 integration flows, Azure Service Bus queue depths,
dead-letter alerts, Application Insights exceptions, and Container Apps metrics.

## Running locally

```bash
uv sync
uv run pybabel compile -d translations
uv run flask --app dashboard.app run
```

Open http://127.0.0.1:5000

If `dashboard/.env` exists, the dashboard loads it automatically at startup.
Values already exported in the shell still take precedence.

### Alarm persistence (Cosmos DB)

Alarm configuration and runtime state are persisted to Azure Cosmos DB via the
`azure-cosmos` SDK (`dashboard/services/cosmos_store.py`). Each alarm namespace
(`alarm1`/`alarm2`/`alarm3`) stores a `config` and a `state` document in a single
container partitioned on `/pk`. Alarm pauses are stored separately, one document per
pause, in the `alarm-pause` partition (see [Alarm pauses](#alarm-pauses)).

For local development, run the Cosmos DB emulator. It lives in the shared Compose stack
under `local/` on the `dashboard` profile:

```bash
cd ../local
docker compose --profile dashboard up -d cosmos-emulator
```

The emulator takes ~1 minute to become healthy. Then run the dashboard on the host via
`uv run flask` (see [Running locally](#running-locally)) — the `dashboard/.env` values
point at the emulator on `https://localhost:8081` using Microsoft's well-known emulator
key (not a secret) and disable TLS verification for the self-signed certificate. The
database and container are created automatically on first use when a key is configured.

In cloud environments, set `COSMOS_ENDPOINT` to the account URI, leave `COSMOS_KEY`
empty to use Managed Identity / service-principal RBAC (data-plane role required), and
set `COSMOS_DISABLE_SSL_VERIFY=false`. The database and container must be provisioned
ahead of time (e.g. via Terraform).

### Example data (local emulator only)

`scripts/seed_example_alarms.py` loads example alarm rules into the emulator: one
Inactivity, Outgoing Volume and Failures rule for every demo flow (`services/demo_data.py`),
with a mix of enabled/disabled rules, thresholds and email settings. `--with-pauses` also
adds example pauses in every state (active, scheduled, indefinite, all flows, ended early,
cancelled).

```bash
uv run python scripts/seed_example_alarms.py                            # add missing example rules
uv run python scripts/seed_example_alarms.py --with-pauses              # ...plus example pauses
uv run python scripts/seed_example_alarms.py --with-pauses --overwrite  # reset example data (e.g. refresh pause times)
uv run python scripts/seed_example_alarms.py --remove                   # delete all example data
```

The script refuses to run unless `COSMOS_ENDPOINT` is a local emulator address. Seeded
rules are tagged `"example": true` and seeded pauses have *Requested by* set to
`Example data (seed script)`, so `--overwrite` and `--remove` never touch rules or pauses
created by hand. The `scripts/` folder is not copied into the Docker image. Rules for the
real flows (PHW, Paris, PIMS, …) match the local flows; the fictional stress-test flows
(Werfen, Radiology, …) only appear as flows with `DEMO_MODE=true`.

## Alarm pauses

Alarms can be paused to stop alerts during planned maintenance or known outages.
While a pause is active the affected rules show as **Paused**, are not evaluated, and
send no alert emails. When the pause ends (or is cancelled) the next evaluation runs as
normal and raises alerts if the alarm condition is still met.

A pause has:

| Setting | Options |
|---------|---------|
| Scope | Single alarm rule, single flow, multiple flows, or all flows. Flow scopes pause all three alarm types and also cover rules added to the flow later. |
| Start | Now, or a future date/time (up to 365 days ahead) |
| End | After a duration, at a date/time, or until cancelled |
| Reason / Requested by | Both required (the dashboard has no user login, so *Requested by* is free text) |

Times are entered and shown in UK time (Europe/London) and stored in UTC. Times that
don't exist when the clocks go forward are rejected.

Where pauses appear:

- **`/alarms/pauses`** — active, scheduled and recently ended (last 7 days) pauses, with
  *End now* / *Cancel* actions and a *Schedule pause* button.
- **Overview (`/`) and Alarms Summary (`/alarms`)** — a "N paused · M scheduled" indicator
  at the top of the page (in the page header, kept live by the page's auto-refresh) linking
  to `/alarms/pauses`.
- **Flows page** — an *Alarms paused* / *Pause scheduled* badge on affected flows, and
  paused alarm chips.
- **Alarm tables and Alarms by Flow** — Pause / Resume buttons per rule, and a note showing
  who paused it and until when, or when the next pause is scheduled. A rule paused as part of
  a flow or all-flows pause shows *Manage pause* instead of *Resume*, because resuming it
  would resume the other alarms too.

Behaviour worth knowing:

- Pauses need Cosmos DB. Creating, cancelling or resuming one returns 503 if Cosmos is not
  configured or unavailable, rather than reporting success without a durable change. If
  pauses can't be *read* during alarm evaluation, alarms are evaluated as if nothing
  is paused, so alerts are never silently lost.
- Alarms are evaluated when pages or `/api/alarms/status` are requested (cached for
  `API_CACHE_TTL`), so a pause takes effect or ends on the next evaluation, not at the exact
  second.
- Ended and cancelled pauses are deleted 30 days after they finish.
- Pauses created before this feature (stored as `paused_until` in the alarm `state`
  document) are still honoured until they expire.

Code: `services/alarm_pauses.py` (model, validation, storage), `services/alarm_base.py`
(`resolve_pause`, used by each alarm evaluator), `routes/alarms.py` (pages and API),
`templates/partials/pause_modal.html`, `templates/partials/pause_macros.html` and
`static/js/alarm-pause.js` (shared UI).

### Pause API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/alarm-pauses` | Pauses grouped as `active` / `scheduled` / `recent`, plus `summary` counts |
| `GET` | `/api/alarm-pauses/options` | Flow and rule picker options for the pause form |
| `POST` | `/api/alarm-pauses` | Create a pause (201) |
| `POST` | `/api/alarm-pauses/<pause_id>/cancel` | Cancel a scheduled pause, or end an active one now |
| `POST` | `/alarm1\|2\|3/pause/<rule_id>` | Pause one rule from now: `{"duration_minutes", "indefinite", "reason", "requested_by"}` |
| `POST` | `/alarm1\|2\|3/unpause/<rule_id>` | Resume one rule (409 with `manage_url` if it is covered by a wider pause) |

Create request body:

```json
{
  "scope_type": "flows",
  "targets": ["phw-to-mpi", "pims-to-mpi"],
  "start": "2026-10-01T22:00",
  "end_mode": "duration",
  "duration_minutes": 240,
  "reason": "Planned network maintenance",
  "requested_by": "Jane Smith"
}
```

- `scope_type`: `rule` (targets are `{"alarm_type": "alarm1", "rule_id": "..."}`), `flows`
  (targets are workflow ids) or `all` (targets ignored).
- `start`: `null` for now, or a UK-time `YYYY-MM-DDTHH:MM`.
- `end_mode`: `duration` (with `duration_minutes`), `until` (with `end`, UK time) or `indefinite`.

Errors return `{"ok": false, "error": "..."}` with 400 (invalid request), 404 (unknown
pause), 409 (rule covered by a wider pause) or 503 (pause storage unavailable).
`/api/alarms/status` also includes a `pause_summary` (`{"active": n, "scheduled": n}`).

## Running with Docker

```bash
docker build -t integration-hub-dashboard .
docker run -p 8080:8080 --env-file dashboard.env integration-hub-dashboard
```

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_TENANT_ID` | Azure AD tenant ID (for service-principal fallback auth) | — |
| `AZURE_CLIENT_ID` | Service principal client ID (for service-principal fallback auth) | — |
| `AZURE_CLIENT_SECRET` | Service principal secret (for service-principal fallback auth) | — |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID | — |
| `AZURE_RESOURCE_GROUP` | Resource group containing Service Bus | — |
| `AZURE_SERVICE_BUS_NAMESPACE` | Service Bus namespace name | — |
| `AZURE_LOG_ANALYTICS_WORKSPACE_ID` | Log Analytics workspace ID | — |
| `AZURE_CONTAINER_APPS_ENVIRONMENT` | Container Apps environment name | — |
| `AZURE_CA_CERT_FILE` | Optional PEM/DER corporate CA certificate file appended to the trust bundle for Azure HTTPS calls | — |
| `FLASK_SECRET_KEY` | Flask session secret | `dev-secret-key-change-in-production` |
| `QUEUE_WARNING_THRESHOLD` | Active message count warning level | `10` |
| `QUEUE_CRITICAL_THRESHOLD` | Active message count critical level | `50` |
| `DLQ_WARNING_THRESHOLD` | Dead-letter count alert level | `1` |
| `API_CACHE_TTL` | Status API cache TTL in seconds | `30` |

All queue names are also overridable (e.g. `QUEUE_PHW_PRE`, `QUEUE_PHW_POST`).
See `dashboard/config.py` for the full list.

### Cosmos DB persistence variables

| Variable | Description | Default |
|----------|-------------|---------|
| `COSMOS_ENDPOINT` | Cosmos account URI (emulator: `https://localhost:8081`). Empty disables persistence. | — |
| `COSMOS_KEY` | Account key. When set, key auth is used and the DB/container are auto-created; empty uses RBAC. | — |
| `COSMOS_DATABASE` | Cosmos database name | `integration-hub` |
| `COSMOS_CONTAINER` | Cosmos container name (partition key `/pk`) | `dashboard` |
| `COSMOS_DISABLE_SSL_VERIFY` | Disable TLS verification — required for the local emulator only | `false` |

## Azure authentication

The dashboard uses `DefaultAzureCredential` first (Managed Identity, Azure CLI login, workload identity, etc.).
If `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are set, it safely falls back to
`ClientSecretCredential`.

This means:
- Local development can use `az login` without client secret values.
- Azure-hosted deployments can use Managed Identity without client secret values.
- Service principal env vars remain supported as a fallback path.

## Quality checks

```bash
bash check.sh
```

Runs ruff, bandit, mypy, and pytest. The Cosmos emulator integration tests are skipped
(see below).

`check.sh` only type-checks `dashboard/`, but CI also type-checks the tests. Before pushing, run:

```bash
uv run mypy --ignore-missing-imports dashboard/ tests/ scripts/
```

### Cosmos emulator integration tests

`tests/test_alarm_pause_emulator.py` runs the alarm pause feature end to end against the
local Cosmos emulator: pauses are created and cancelled through the Flask routes, stored in
the emulator and read back by the real Alarm 3 evaluator, which is checked for sending (or
not sending) an alert email. Only Log Analytics and the email transport are stubbed.

The tests are skipped unless `RUN_COSMOS_EMULATOR_TESTS=1`, so `check.sh` and CI never run
them. With the emulator running and `COSMOS_*` set in `.env`:

```bash
RUN_COSMOS_EMULATOR_TESTS=1 uv run pytest tests/test_alarm_pause_emulator.py -v
```

- They refuse to run unless `COSMOS_ENDPOINT` is a local emulator address, and skip if the
  emulator is unreachable.
- Each test uses a throwaway `itest-<id>` flow and removes its rule, alarm state and pauses
  afterwards, so existing local data is left alone.
- They skip if an active all-flows pause exists (for example from
  `seed_example_alarms.py --with-pauses`); clear it with `--remove` or the Alarm Pauses page.
