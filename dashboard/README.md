# Integration Hub Dashboard

NOC monitoring dashboard for the NHS Wales Integration Hub.

Provides real-time visibility of all HL7 integration flows, Azure Service Bus queue depths,
dead-letter alerts, Application Insights exceptions, and Container Apps metrics.

## Running locally

```bash
uv sync
uv run flask --app dashboard.app run
```

Open http://127.0.0.1:5000

## Running with Docker

```bash
docker build -t integration-hub-dashboard .
docker run -p 8080:8080 --env-file dashboard.env integration-hub-dashboard
```

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_TENANT_ID` | Azure AD tenant ID | — |
| `AZURE_CLIENT_ID` | Service principal client ID | — |
| `AZURE_CLIENT_SECRET` | Service principal secret | — |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID | — |
| `AZURE_RESOURCE_GROUP` | Resource group containing Service Bus | — |
| `AZURE_SERVICE_BUS_NAMESPACE` | Service Bus namespace name | — |
| `AZURE_LOG_ANALYTICS_WORKSPACE_ID` | Log Analytics workspace ID | — |
| `AZURE_CONTAINER_APPS_ENVIRONMENT` | Container Apps environment name | — |
| `FLASK_SECRET_KEY` | Flask session secret | `dev-secret-key-change-in-production` |
| `QUEUE_WARNING_THRESHOLD` | Active message count warning level | `10` |
| `QUEUE_CRITICAL_THRESHOLD` | Active message count critical level | `50` |
| `DLQ_WARNING_THRESHOLD` | Dead-letter count alert level | `1` |
| `API_CACHE_TTL` | Status API cache TTL in seconds | `30` |

All queue names are also overridable (e.g. `QUEUE_PHW_PRE`, `QUEUE_PHW_POST`).
See `dashboard/config.py` for the full list.

## Quality checks

```bash
bash check.sh
```

Runs ruff, bandit, mypy, and pytest.
