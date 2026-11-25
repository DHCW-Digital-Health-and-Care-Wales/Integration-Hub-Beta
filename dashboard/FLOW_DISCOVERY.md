# Flow Discovery — NOC Dashboard

## Overview

The NOC dashboard discovers the integration flows deployed in Azure at runtime
instead of using a hardcoded list. When a flow is deployed via Terraform it
appears on the dashboard after the next discovery refresh, with no code change.

Discovery lives in `dashboard/services/arm.py`. It lists every Container App in
`AZURE_CONTAINER_APPS_RESOURCE_GROUP` through the Container Apps management API
and reads, per app:

- its Service Bus env vars (`WORKFLOW_ID`, `MICROSERVICE_ID`,
  `INGRESS_/EGRESS_QUEUE_NAME`, `INGRESS_/EGRESS_TOPIC_NAME`, `WRRS_TOPIC_NAME`,
  `INGRESS_SUBSCRIPTION_NAME`, `RECEIVER_MLLP_HOST/PORT`), which decide the
  app's role (server, transformer, sender, ...) and the queues/topics it uses;
- its `integration-hub-flow` resource tag, which decides **which flows the app
  belongs to**.

Only apps with a `WORKFLOW_ID` env var are considered.

---

## Flow membership

`WORKFLOW_ID` is the app's **telemetry identity**: `event_logger_lib` and
`metric_sender_lib` stamp it on every event and metric, and alarm rules and
pauses are stored against it. A Container App can only have one, but a server
that publishes to a shared topic feeds several flows. For example, the WDS
server (`WORKFLOW_ID=wds-to-mpi`) publishes to the WDS input topic, which
`wds-to-mpi`, `wds-to-wis` and `wds-to-phw` each subscribe to.

The `integration-hub-flow` tag carries **flow membership** as a comma-separated
list of flow IDs:

| App                  | `WORKFLOW_ID`  | `integration-hub-flow` tag                           |
|----------------------|----------------|------------------------------------------------------|
| WDS HL7 server       | `wds-to-mpi`   | `wds-to-mpi,wds-to-wis,wds-to-phw`                   |
| WDS → WIS transformer| `wds-to-wis`   | `wds-to-wis`                                         |
| WDS → PHW sender     | `wds-to-phw`   | `wds-to-phw`                                         |

Rules (`arm.parse_flow_tag`, `arm.resolve_flow_ids`):

1. Entries are trimmed, lower-cased and de-duplicated; entries that are not
   valid flow IDs are dropped. Tag names are matched case-insensitively.
2. A listed flow is kept only if some deployed app has that `WORKFLOW_ID`.
   Telemetry, alarm rules and pauses are all keyed by `WORKFLOW_ID`, so every
   flow must be one. This also stops a stale tag (such as the old
   `mpi-outbound` value) from inventing a flow.
3. A tagged app does not have to list its own `WORKFLOW_ID`. The MPI server's
   `WORKFLOW_ID` (`mpi-to-topic`) is its telemetry identity, not a flow, so its
   tag lists only the downstream flows it feeds.
4. With no tag, or no usable entries, the app belongs to its `WORKFLOW_ID` flow.

An app joins every flow it belongs to. Each flow is then built from its member
apps only (`arm._build_flow`), so a flow on a shared topic lists only its own
subscriptions, transformer and sender, and takes its source host/port from the
shared server.

### Untagged consumers on a shared topic

If a publisher's tag does not list a consumer's flow, that consumer's flow has
no server. Flows consisting only of subscription senders are then merged into
the flow that owns the topic (`arm._merge_subscription_sender_flows`), as before
tagging existed. Tag the publisher to show such a flow on its own.

### Why a tag rather than another env var

- Changing a tag does not create a new Container App revision, so membership can
  be corrected without restarting the services.
- Tags come back in the same `list_by_resource_group` call the dashboard already
  makes, so no extra ARM calls or RBAC are needed.

Azure limits a tag value to 256 characters (roughly 15 flow IDs).

---

## Terraform

Tags are set at the module call in each `components/app-platform/flow_*.tf`
file. Most apps carry their own flow ID:

```hcl
tags = merge(local.tags, { "integration-hub-flow" = "wds-to-wis" })
```

Shared publishers list every deployed flow that consumes their topic(s),
including their own `WORKFLOW_ID` only when that is a real flow:

```hcl
wds_hl7_server_flow_tag = join(",", concat(
  local.wds_to_mpi_enabled ? ["wds-to-mpi"] : [],
  local.wds_to_wis_enabled ? ["wds-to-wis"] : [],
  local.wds_to_phw_enabled ? ["wds-to-phw"] : [],
))

tags = merge(local.tags, {
  "integration-hub-flow" = each.key == "wds_hl7_server" ? local.wds_hl7_server_flow_tag : "wds-to-mpi"
})
```

| Shared publisher | File                   | Flows listed                                              |
|------------------|------------------------|-----------------------------------------------------------|
| WDS HL7 server   | `flow_wds_to_mpi.tf`   | `wds-to-mpi`, `wds-to-wis`, `wds-to-phw`                  |
| LIMS REST server | `flow_lims_to_mpi.tf`  | `lims-to-hub`, `lims-to-trrr`, `lims-to-wrrs`             |
| PMS HL7 server   | `flow_pms_to_mpi.tf`   | `pms-to-mpi`, `cav-pms-to-wcrs`                           |
| RISP REST server | `flow_risp_to_mpi.tf`  | `risp-to-mpi`, `risp-to-wrrs` (publishes to two topics)   |
| MPI HL7 server   | `flow_mpi_outbound.tf` | `sww-to-chemo`, `bcu-to-chemo`, `mpi-to-phw` (not its own `mpi-to-topic`) |

Each flow is only listed when it is deployed in that environment.

### Adding a flow that consumes an existing topic

1. Give the new consumer apps their own `WORKFLOW_ID` and tag them with it.
2. Add the new flow ID to the publisher's tag list (guarded by the flow's
   `*_enabled` local).
3. Optionally add display metadata (label, source, destination, colour, icon) to
   `_DISPLAY_META` in `dashboard/services/arm.py`; otherwise a label is derived
   from the flow ID.

---

## What uses flow membership

| Area | Behaviour |
|------|-----------|
| Overview / Flows pages | One card per flow, built from its member apps. A shared server's topic backlog counts towards each flow it feeds. |
| Container Apps metrics | A shared app is listed under every flow it belongs to (`container_apps.get_container_apps_metrics`). |
| Messages page filter | A shared topic maps to every flow using it (`flows.entity_to_flow_ids`). |
| Network Testing | Each flow gets its own sender destination, so fan-out destinations are no longer hidden behind the first sender. |
| Alarm config | Every discovered flow can be selected. Alarm queries still filter on the `workflow_id` written by each app, so a fan-out flow's inbound/outbound/failure alarms come from its own transformer and sender events. Events from a publisher whose `WORKFLOW_ID` is not a flow (the MPI server's `mpi-to-topic`) are not shown on any flow card, but alarms for that ID still work: existing rules stay selectable and new ones can be added by entering the ID. |

---

## Fallback behaviour

- **Demo mode** (`DEMO_MODE=true`): synthetic flows from `demo_data.py`.
- **Container Apps API not configured or unreachable**: static `_FLOW_DEFS` in
  `dashboard/services/flows.py`, with queue/topic names resolved by suffix
  against the Service Bus namespace. If discovery fails after a successful
  run, the last cached result is used.

---

## Refreshing

| Cache                         | TTL        | Override                        |
|-------------------------------|------------|---------------------------------|
| Status data (queues etc.)     | 30 seconds | `?force=true` on `/api/status`  |
| Container App flow discovery  | 5 minutes  | `GET /api/refresh`              |

Flow definitions are built once per process. `GET /api/refresh` re-reads the
Container Apps and rebuilds the flow definitions, so a tag change shows without
restarting the dashboard. The response includes an `active_flows` list.

---

## Required Azure RBAC

The dashboard identity needs `Reader` on the Container Apps resource group to
list Container Apps with their env vars and tags. This is the same role already
needed for Container Apps metrics, so no extra RBAC is required.
