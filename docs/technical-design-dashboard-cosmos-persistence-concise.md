# Technical Design — Dashboard Data Persistence (Azure Cosmos DB)

**Story:** NOC Dashboard — Alarm Config & State Persistence  
**Component:** `dashboard/`

---

## Problem

Alarm configuration and runtime state were stored as JSON files on the container's local filesystem. These are lost on every restart or redeployment, not safe under concurrent Gunicorn workers, and inaccessible without `exec`-ing into the container.

---

## Solution

Persist alarm config and state to **Azure Cosmos DB (NoSQL / SQL API)** with serverless capacity. Each of the three alarm services stores two small documents — `config` and `state` — in a single container partitioned by alarm namespace. Authentication uses Managed Identity data-plane RBAC in cloud environments and account-key auth against the local emulator.

The dashboard degrades gracefully when `COSMOS_ENDPOINT` is not set: all read/write operations are no-ops and alarm pages render with empty defaults.

---

## Data Model

**Container:** `alarms` in database `integration-hub`, partition key `/pk`.

Six documents total:

| Partition (`pk`) | Document `id` | Contents |
|---|---|---|
| `alarm1` | `config` | Rule thresholds and enabled flags |
| `alarm1` | `state` | Last-fired timestamps, pause state |
| `alarm2` | `config` | Rule thresholds and enabled flags |
| `alarm2` | `state` | Last-fired timestamps, pause state |
| `alarm3` | `config` | Rule thresholds and enabled flags |
| `alarm3` | `state` | Last-fired timestamps, pause state |

Document payloads mirror the previous JSON file structure (`{"rules": {...}}`). Cosmos system fields (`_rid`, `_etag` etc.) and routing keys (`id`, `pk`) are stripped on read.

---

## Code Structure

| Module | Responsibility |
|---|---|
| `cosmos_store.py` | Cosmos client singleton, `get_document()`, `upsert_document()` |
| `alarm_base.py` | Shared `load_config/save_config/load_state/save_state` + pause helpers |
| `alarm1/2/3.py` | Thin public wrappers; each defines its own `COSMOS_PK` constant |

The `CosmosClient` is created once per process and reused (SDK best practice). Thread-safety on initialisation is ensured via `threading.Lock` with double-check locking.

---

## Authentication

**Cloud:** `COSMOS_KEY` is not set → `DefaultAzureCredential` / Managed Identity. The account has `local_authentication_disabled = true` (key auth blocked at the account level). The dashboard's user-assigned managed identity is granted the built-in **Cosmos DB Built-in Data Contributor** role (`...0002`) via Terraform.

> Cosmos data-plane RBAC does **not** resolve Entra group membership — role assignments must be to individual object IDs.

**Local:** `COSMOS_KEY` set to the well-known emulator key. TLS verification and endpoint discovery are disabled (emulator uses a self-signed cert and advertises an unreachable internal container IP).

---

## Infrastructure (Terraform)

Provisioned via the reusable module `modules/terraform-azurerm-cosmosdb` called from `components/app-platform/cosmosdb.tf`.

- **Capacity:** Serverless (billed per request unit, negligible cost for this workload).
- **Feature flag:** `deploy_noc_dashboard_cosmos` defaults to `false` — existing environments are unaffected until they opt in via tfvars.
- **Env vars injected automatically:** `COSMOS_ENDPOINT`, `COSMOS_DATABASE`, `COSMOS_CONTAINER`, `COSMOS_DISABLE_SSL_VERIFY=false`. `COSMOS_KEY` is intentionally omitted.
- **Network:** `public_network_access_enabled` is configurable per environment; private endpoint is supported and recommended for production.

---

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `COSMOS_ENDPOINT` | _(empty)_ | Empty disables persistence entirely |
| `COSMOS_KEY` | _(empty)_ | Empty → Managed Identity RBAC |
| `COSMOS_DATABASE` | `integration-hub` | |
| `COSMOS_CONTAINER` | `alarms` | |
| `COSMOS_DISABLE_SSL_VERIFY` | `false` | `true` only for local emulator |

---

## Local Development

```bash
cd local
docker compose --profile dashboard up -d cosmos-emulator

cd dashboard
uv run flask --app dashboard.app run
```

The emulator runs on `localhost:8081`. On first use, key-auth triggers `create_database_if_not_exists` / `create_container_if_not_exists` — no manual setup required.

---

## Testing

`dashboard/tests/test_cosmos_store.py` tests the persistence layer with the SDK fully mocked. A `conftest.py` autouse fixture patches `COSMOS_ENDPOINT = ""` for all tests to prevent any real network access regardless of the local `.env` file.

---

## Security

- No account key in cloud — Managed Identity only. `local_authentication_disabled = true` enforces this at the account level.
- TLS verification is only disabled when the endpoint is `localhost`/`127.0.0.1`/`cosmos-emulator`; any attempt against a non-local endpoint is logged as an error and blocked.
- Dashboard MI granted Data Contributor only — minimum required privilege for read/write operations.
