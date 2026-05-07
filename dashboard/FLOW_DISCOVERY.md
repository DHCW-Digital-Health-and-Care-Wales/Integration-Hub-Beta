# Dynamic Flow Discovery — NOC Dashboard

## Overview

The NOC dashboard automatically discovers which integration flows are currently
deployed in Azure, rather than showing a fixed hardcoded list. When a new flow
is deployed via Terraform, it will appear on the dashboard after the next
refresh — with no code changes required.

This is achieved by tagging every Container App with an `integration-hub-flow`
Azure resource tag, and having the dashboard query the Azure Resource Manager
(ARM) API to read those tags at runtime.

---

## How It Works

```
Terraform deploys Container Apps
          │
          │  tags = merge(local.tags, {
          │    "integration-hub-flow" = "phw-to-mpi"
          │  })
          ▼
  Azure Container Apps
  (each tagged with flow ID)
          │
          │  ARM API: list_by_resource_group()
          │  reads app.tags["integration-hub-flow"]
          ▼
  dashboard/services/arm.py
  → returns set of deployed flow IDs
          │
          ▼
  dashboard/services/flows.py  get_active_flows()
  → filters FLOWS dict to deployed only
          │
          ▼
  Dashboard renders only live flows
```

### Fallback behaviour

If ARM credentials are not configured (e.g. local development) or the ARM call
fails for any reason, `get_active_flows()` returns the full `FLOWS` dict so the
dashboard continues to display all known flows. This means the dashboard
**degrades gracefully** rather than showing a blank page.

---

## Tag Schema

A single tag is applied to every Container App that belongs to an integration flow:

| Tag key                 | Example value     | Description                        |
|-------------------------|-------------------|------------------------------------|
| `integration-hub-flow`  | `phw-to-mpi`      | Unique slug identifying the flow   |

### Flow ID reference

| Flow ID            | Label            | Source port |
|--------------------|------------------|-------------|
| `phw-to-mpi`       | PHW → MPI        | 2575        |
| `paris-to-mpi`     | Paris → MPI      | 2577        |
| `chemocare-to-mpi` | ChemoCare → MPI  | 2578        |
| `pims-to-mpi`      | PIMS → MPI       | 2579        |
| `wds-to-mpi`       | WDS → MPI        | 2582        |
| `mpi-outbound`     | MPI Outbound     | —           |

---

## Terraform Changes

The tag is applied at the module call site in each flow file under
`components/app-platform/`.  The change is a one-line merge per flow:

```hcl
# Before
tags = local.tags

# After
tags = merge(local.tags, { "integration-hub-flow" = "phw-to-mpi" })
```

### Files changed

| File                          | Tag value added        |
|-------------------------------|------------------------|
| `flow_phw_to_mpi.tf`          | `phw-to-mpi`           |
| `flow_paris_to_mpi.tf`        | `paris-to-mpi`         |
| `flow_chemocare_to_mpi.tf`    | `chemocare-to-mpi`     |
| `flow_pims_to_mpi.tf`         | `pims-to-mpi`          |
| `flow_mpi_outbound.tf`        | `mpi-outbound`         |
| `flow_wds_to_mpi.tf`          | `wds-to-mpi`           |

No changes to the container app module (`modules/terraform-azurerm-container-app`)
were needed — `tags` is already passed through from `var.tags` to the resource.

---

## Dashboard Changes

### New file: `dashboard/services/arm.py`

Queries ARM for all Container Apps in the configured resource group and returns
the set of `integration-hub-flow` tag values found.

Results are **cached for 5 minutes** to avoid querying ARM on every page load.
Use the `/api/refresh` endpoint (see below) to force an immediate re-query.

```
Required env vars (already used by the rest of the dashboard):
  AZURE_TENANT_ID
  AZURE_CLIENT_ID
  AZURE_CLIENT_SECRET
  AZURE_SUBSCRIPTION_ID
  AZURE_CONTAINER_APPS_RESOURCE_GROUP
```

### Updated: `dashboard/services/flows.py`

- **`FLOWS` dict** — added `wds-to-mpi` (port 2582, orange `#f97316`).
- **`get_active_flows(force_refresh=False)`** — new function that calls
  `arm.get_deployed_flow_ids()` and filters `FLOWS` to only deployed flows.
- **`build_flow_data(queues, flows=None)`** and **`flow_health(..., flows=None)`**
  — now accept an explicit `flows` dict so they operate on the active subset.

### Updated: `dashboard/dashboard/config.py`

Two new environment variables for the WDS flow queues:

| Variable        | Default              |
|-----------------|----------------------|
| `QUEUE_WDS_PRE` | `pre-wds-transform`  |
| `QUEUE_WDS_POST`| `post-wds-transform` |

### Updated: `dashboard/dashboard/app.py`

- `_build_status()` and `flows_page()` now call `get_active_flows()` instead
  of using the static `FLOWS` dict directly.
- New **`/api/refresh`** endpoint (see below).

---

## Adding a New Flow

To add a new integration flow and have it appear on the dashboard automatically:

### Step 1 — Add the tag in Terraform

In the new flow's `.tf` file (e.g. `flow_newflow_to_mpi.tf`), add the tag to
the module call:

```hcl
module "container_apps_newflow_to_mpi" {
  source   = "../../modules/terraform-azurerm-container-app"
  for_each = local.container_apps_newflow_to_mpi

  tags = merge(local.tags, { "integration-hub-flow" = "newflow-to-mpi" })
  # ... rest of arguments unchanged
}
```

### Step 2 — Add flow metadata to the dashboard

In `dashboard/dashboard/services/flows.py`, add an entry to the `FLOWS` dict:

```python
"newflow-to-mpi": {
    "label": "NewFlow → MPI",
    "source": "NewFlow",
    "source_port": 2583,                  # the MLLP port
    "pre_queue":  config.QUEUE_NEWFLOW_PRE,
    "transformer": "NewFlow Transformer", # or None
    "post_queue": config.QUEUE_NEWFLOW_POST,
    "destination": "MPI",
    "colour": "#your-colour",
    "icon": "bi-bootstrap-icon-name",
},
```

And add the queue env vars to `config.py`:

```python
QUEUE_NEWFLOW_PRE  = os.getenv("QUEUE_NEWFLOW_PRE",  "pre-newflow-transform")
QUEUE_NEWFLOW_POST = os.getenv("QUEUE_NEWFLOW_POST", "post-newflow-transform")
```

### Step 3 — Deploy

Once Terraform is applied and the Container Apps are running with the new tag,
visit `/api/refresh` on the dashboard to force-refresh the ARM cache and display
the new flow immediately.

---

## API Endpoints

### `GET /api/refresh`

Force-refreshes both the ARM flow discovery cache and the status data cache.
Returns the full status payload plus an `active_flows` list.

```json
{
  "refreshed": true,
  "active_flows": ["phw-to-mpi", "pims-to-mpi", "chemocare-to-mpi"],
  "system_health": "healthy",
  "kpis": { ... },
  "flows": [ ... ],
  "queues": [ ... ]
}
```

Use this after deploying a new flow to see it on the dashboard without waiting
for the 5-minute ARM cache TTL to expire.

### `GET /api/status?force=true`

Forces a refresh of the status data (queue depths, health) but does **not**
re-query ARM for flow discovery.

---

## Cache TTLs

| Cache                     | TTL        | Override                   |
|---------------------------|------------|----------------------------|
| Status data (queues etc.) | 30 seconds | `?force=true` on `/api/status` |
| ARM flow discovery        | 5 minutes  | `GET /api/refresh`          |

The ARM TTL is deliberately longer since deployed flows change rarely — only
when Terraform is applied.

---

## Required Azure RBAC

The service principal used by the dashboard (`AZURE_CLIENT_ID`) needs the
following permission to list Container Apps:

| Role                      | Scope                 |
|---------------------------|-----------------------|
| `Reader`                  | Resource group        |

The `Reader` role grants read-only access to list resources and their tags.
The dashboard already requires this role for existing Container Apps metrics
functionality (`azure_monitor.py`), so no additional RBAC changes are needed.
