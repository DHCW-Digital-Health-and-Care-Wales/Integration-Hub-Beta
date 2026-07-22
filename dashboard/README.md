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
container partitioned on `/pk`.

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
| `COSMOS_DATABASE` | Cosmos database name | `integration-hub-dashboard` |
| `COSMOS_CONTAINER` | Cosmos container name (partition key `/pk`) | `alarms` |
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

Runs ruff, bandit, mypy, and pytest.
