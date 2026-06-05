# Replay Browser — Azure Deployment Design

How the `replay_browser` service would be deployed into the NHS Wales Integration
Hub Azure environments (DEV → PRD/DR), based on the existing Terraform patterns
in [Integration-Hub-Terraform](https://dev.azure.com/) (`components/app-platform/`).

> Status: design only. `replay_browser` currently exists as a local-only service
> under the `tools` Docker Compose profile. No Terraform exists for it yet.

---

## 1. Deployment Model

The service follows the same shape as the existing NOC dashboard
(`components/app-platform/noc_dashboard.tf`) crossed with the message replay
job wiring (`components/app-platform/message_replay.tf`):

| Concern | Pattern to copy |
|---|---|
| Compute | Single Azure Container App in the existing Container Apps Environment, `gunicorn` on port 8080 |
| Image | Built and pushed to existing ACR as `replay-browser:<env>`, pulled via the `acr_pull_mi` user-assigned identity |
| Ingress | HTTPS, `external_enabled = true` (or internal-only if scoped to the NHS network) — same shape as the NOC dashboard |
| Identity | System-assigned (for Container Apps Jobs Operator role) + `msg_store_db_mi` (SQL DB access) |
| Secrets | `FLASK_SECRET_KEY` via a new `var.replay_browser_flask_secret_key` (mirrors `dashboard_flask_secret_key`) |
| Feature flag | New `var.deploy_replay_browser` bool + `local.replay_browser_enabled` gate |

---

## 2. RBAC

| Scope | Role | Why |
|---|---|---|
| SQL DB (`monitoring.Message`, `monitoring.MessageReplayQueue`) | Reuse existing `msg_store_db_mi` SQL grants | Read messages, insert replay queue rows |
| `azurerm_container_app_job.message_replay_job[0].id` | **Container Apps Jobs Operator** | Required for the in-app "Run now" button to call `jobs.begin_start` with a `REPLAY_BATCH_ID` env override |
| App resource group | `Reader` *(optional)* | Surface job run status in the UI |
| Service Bus | *(none)* | App only writes SQL; `message_replay_job` drains the queue |

Only the **Container Apps Jobs Operator** assignment is genuinely new — the SQL
identity already exists and is reused.

---

## 3. New Terraform File (sketch)

A new `components/app-platform/replay_browser.tf`, mirroring `noc_dashboard.tf`:

```hcl
locals {
  replay_browser_enabled = (
    var.deploy_apps
    && var.deploy_replay_browser
    && var.message_store_sql_deployment_key != null
    && contains(keys(var.sql_deployments), var.message_store_sql_deployment_key)
  )

  container_app_replay_browser_name = "${var.primary_region_infix}-${var.environment}-replay-browser-ca"
  image_name_replay_browser         = "replay-browser"
}

module "container_apps_replay_browser" {
  source   = "../../modules/terraform-azurerm-container-app"
  for_each = local.replay_browser_enabled ? { replay_browser = {} } : {}

  name                         = local.container_app_replay_browser_name
  resource_group_name          = local.app_rg_name
  container_app_environment_id = module.container_apps_environment.containerAppsEnvironmentId
  workload_profile_name        = length(var.workload_profiles) > 0 ? var.workload_profiles[0].name : null
  tags                         = merge(local.tags, { "integration-hub-component" = "replay-browser" })
  condition                    = local.replay_browser_enabled

  acr_pull_identity_id = azurerm_user_assigned_identity.managed_identity["acr_pull_mi"].id
  user_assigned_identity_ids = [
    azurerm_user_assigned_identity.managed_identity["app_insights_metrics_mi"].id,
    azurerm_user_assigned_identity.managed_identity["msg_store_db_mi"].id,
  ]
  container_registry_server = "${var.acr_name}.azurecr.io"

  container_name  = local.container_app_replay_browser_name
  container_image = "${var.acr_name}.azurecr.io/${local.image_name_replay_browser}:${local.image_environment}"

  environment_variables = [
    { name = "SQL_SERVER",                  value = module.sql_database[var.message_store_sql_deployment_key].sql_server_fqdn },
    { name = "SQL_DATABASE",                value = module.sql_database[var.message_store_sql_deployment_key].database_name },
    { name = "MANAGED_IDENTITY_CLIENT_ID",  value = azurerm_user_assigned_identity.managed_identity["msg_store_db_mi"].client_id },
    { name = "FLASK_SECRET_KEY",            value = var.replay_browser_flask_secret_key },
    { name = "AZURE_SUBSCRIPTION_ID",       value = data.azurerm_client_config.current.subscription_id },
    { name = "REPLAY_JOB_RESOURCE_GROUP",   value = local.app_rg_name },
    { name = "REPLAY_JOB_NAME",             value = local.container_app_job_message_replay_name },
  ]

  ingress = {
    enabled          = true
    target_port      = 8080
    exposed_port     = null
    external_enabled = true
    transport        = "http"
  }

  health_probes = local.disabled_health_probes
}

resource "azurerm_role_assignment" "replay_browser_jobs_operator" {
  count = local.replay_browser_enabled && local.message_replay_enabled ? 1 : 0

  scope                = azurerm_container_app_job.message_replay_job[0].id
  role_definition_name = "Container Apps Jobs Operator"
  principal_id         = module.container_apps_replay_browser["replay_browser"].container_app_identity[0].principal_id
}
```

### Variables to add (`variables.tf`)

```hcl
variable "deploy_replay_browser" {
  description = "Deploy the Replay Browser web app"
  type        = bool
  default     = false
}

variable "replay_browser_flask_secret_key" {
  description = "Flask session secret for the Replay Browser"
  type        = string
  sensitive   = true
}
```

---

## 4. Application Changes Required

- Drop in `gunicorn` config matching the dashboard (`--workers 2 --timeout 60`)
  — already done in `replay_browser/Dockerfile`.
- Replace any connection-string-based SQL auth with `DefaultAzureCredential`
  and token-based `pyodbc` auth using `MANAGED_IDENTITY_CLIENT_ID` (same approach
  as `message_store_service`).
- Read all config from `os.getenv()` only — no `.env` files in production
  containers.
- Add the in-app replay trigger module per
  [`IN_APP_REPLAY_DESIGN.md`](./IN_APP_REPLAY_DESIGN.md) (Option C — calls
  `ContainerAppsAPIClient.jobs.begin_start`).

---

## 5. CI/CD

- Add the image build + ACR push to the existing build pipeline alongside
  `dashboard` and `buswatch`.
- Add `replay_browser` to any service loops in `pipeline-ado/`.
- No new pipeline file required.

---

## 6. Environment Rollout

Recommend gating with `deploy_replay_browser` per environment:

| Environment | `deploy_replay_browser` | Notes |
|---|---|---|
| DEV | `true` | Initial rollout, in-app trigger enabled |
| DTE / TST | `true` | Integration test coverage |
| UAT | `true` (read-only first) | Validate UI with end users |
| PPD | `false` initially | Enable only after sign-off on the write surface |
| PRD | `false` initially | Same — Replay Browser is a **write** surface that re-sends patient data |
| DR | `false` | Mirror PRD |

Unlike the NOC dashboard (read-only), Replay Browser can trigger HL7 message
re-delivery, so production enablement should be staged behind explicit
clinical-safety / change-board approval.

---

## 7. Related Documents

- [`IN_APP_REPLAY_DESIGN.md`](./IN_APP_REPLAY_DESIGN.md) — design for the
  in-app "Run now" replay trigger
- `components/app-platform/noc_dashboard.tf` — reference pattern for the
  Container App
- `components/app-platform/message_replay.tf` — existing replay job that this
  app will trigger
- `components/app-platform/message_store_service.tf` — reference pattern for
  SQL DB access via managed identity
