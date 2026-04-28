# Integration Hub — Alert Configuration Strategy

**Status:** Discussion document  
**Audience:** Platform team, infrastructure, clinical informatics support  
**Context:** The Integration Hub currently manages alert rules in Terraform. Support staff need the ability to tune alert thresholds in production without triggering a Terraform deployment — but each deployment currently resets any manual changes back to the repository state.

---

## The Problem

```
Support staff adjust threshold in Azure Portal
          ↓
Next Terraform deployment (pipeline, hotfix, infra change)
          ↓
Alert config reset to whatever is in the repo
          ↓
Threshold is wrong again — silently
```

This is a classic **config drift** problem. The root cause is that Terraform treats alert rules as infrastructure state: anything not in the codebase is either destroyed or reverted on the next `apply`. Support staff changes live outside that state.

Secondary issues:
- No audit trail for who changed what threshold and why
- No way to validate a change before it goes live
- If the threshold causes alert storms, rollback requires another Terraform run
- In a DR scenario, alert rules need to follow the workload — but they're baked into a single region's Terraform state

---

## Option 1 — Terraform `lifecycle { ignore_changes }`

**What it does:** Tells Terraform to create the alert rule on first apply but never update it again.

```hcl
resource "azurerm_monitor_metric_alert" "queue_depth" {
  name     = "queue-depth-warning"
  # ... initial definition ...

  lifecycle {
    ignore_changes = [
      criteria,        # thresholds
      action,          # notification targets
      description,
    ]
  }
}
```

**Pros:**
- Zero new infrastructure — purely a Terraform annotation
- Simple to implement immediately
- Support staff changes in the portal are preserved across deployments

**Cons:**
- Terraform loses visibility of the live config — drift goes undetected forever
- No audit trail (portal changes are logged in Azure Activity Log, but not your own audit system)
- No way to programmatically restore thresholds after a DR failover — you'd need to recreate them manually in the new region
- New alert rules still require a Terraform change

**Verdict:** Good tactical fix for the immediate problem. Not a long-term strategy.

---

## Option 2 — Azure-Native Alert Management (Recommended baseline)

Azure Monitor has several features that separate *what to alert on* from *how to respond* — use them deliberately.

### 2a. Action Groups (already separated)

Action Groups define notification targets (email, SMS, webhook, ITSM). Keep these in Terraform — they change rarely and belong in infrastructure-as-code. Alert rules reference Action Groups by ID, so you can change who gets notified without touching the rule.

### 2b. Alert Processing Rules (suppression & routing)

Azure Monitor [Alert Processing Rules](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-processing-rules) let support staff:
- Suppress alerts during maintenance windows
- Route alerts to different Action Groups without changing the alert rule itself
- Apply time-based filters (only alert between 08:00–18:00)

These exist as a separate Azure resource type and can be managed entirely outside Terraform — support staff use the portal or a simple script.

```hcl
# Terraform owns the rule; support staff own the processing rules
resource "azurerm_monitor_alert_processing_rule_suppression" "maintenance" {
  # intentionally left unmanaged — or managed separately
}
```

### 2c. Scheduled Query Rules with dynamic thresholds

Azure Monitor supports [dynamic thresholds](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-dynamic-thresholds) that learn from historical data automatically. This reduces the need for manual threshold tuning entirely for some alert types (queue depth spikes, message rate anomalies).

**Pros:** No manual threshold maintenance once tuned; adapts to changing volumes.  
**Cons:** Less predictable; requires data history to be useful; not suitable for hard compliance thresholds.

---

## Option 3 — Config Microservice (Config Container)

Extract alert configuration into a dedicated configuration service backed by a persistent store (Azure SQL or Azure Table Storage). The dashboard (or a separate config service) exposes a UI/API for support staff to manage thresholds. Alert rules then query this service for their thresholds at evaluation time — or the config service drives the alerts directly.

### Architecture

```
┌─────────────────────────────────────────────┐
│  NOC Dashboard (or separate Config Service) │
│                                             │
│  /admin/alerts — threshold management UI   │
│         ↓                                  │
│  Azure SQL / Table Storage                 │
│  (alert_rules table: name, threshold,      │
│   severity, enabled, modified_by, ts)      │
└──────────────────────┬──────────────────────┘
                       │
         ┌─────────────▼──────────────┐
         │  Alert Evaluator           │
         │  (runs on schedule or      │
         │   triggered by Service Bus │
         │   metrics)                 │
         │                            │
         │  reads thresholds from DB  │
         │  → fires Action Group      │
         └────────────────────────────┘
```

### What lives where

| Concern | Owner | Store |
|---------|-------|-------|
| Alert rule structure (what metric, what resource) | Terraform | IaC repo |
| Thresholds and severity levels | Config service | Azure SQL / Table Storage |
| Notification targets (email, SMS) | Terraform (Action Groups) | IaC repo |
| Suppression windows | Support staff | Config service DB |
| Audit log | Config service | Azure SQL |

### Pros
- Full audit trail: who changed what, when, and why (with a comment field)
- No Terraform required for day-to-day threshold changes
- Config survives deployments — Terraform never touches the threshold store
- Can validate changes before applying (e.g., "this threshold would have fired 47 times yesterday")
- Supports approval workflows if needed

### Cons
- New service to build, deploy, and maintain
- Alert evaluation depends on the config service being available — adds a reliability dependency
- More complex than native Azure alerting

**Verdict:** Best long-term option if support staff need frequent, auditable changes. A lightweight version could be added to the existing dashboard rather than as a separate container.

---

## Option 4 — Alert Container (Dedicated Alerting Service)

A standalone microservice whose *sole responsibility* is alert evaluation and notification. It replaces Azure Monitor alert rules entirely for application-level alerts (queue depth, message rates, exception rates).

### How it works

```
Azure Service Bus metrics ──┐
                             ├──→ Alert Container ──→ Action Group / Teams webhook
Azure Monitor Log Analytics ┘     (evaluates rules        / PagerDuty / ITSM
                                   from config DB)
```

The alert container:
- Runs on a schedule (e.g., every 60 seconds)
- Fetches current queue depths, exception rates
- Compares against thresholds stored in its config DB
- Fires notifications via Action Groups or direct webhooks
- Writes alert history to SQL

### Pros
- Completely decoupled from Azure infrastructure state
- Full control over alert logic (multi-condition, correlation, suppression)
- Can alert on application-level patterns Azure Monitor can't natively express (e.g., "no messages processed on flow X for 30 minutes during business hours")
- Thresholds are just data — change them via UI or API at any time
- Alert history available for reporting and trend analysis

### Cons
- Rebuilds functionality Azure Monitor already provides natively
- Must be highly available — if the alert container is down, you get no alerts
- Requires DR consideration itself (if it goes down, who watches the watcher?)

**Verdict:** Powerful but expensive to build and maintain. Most valuable for complex, application-aware alert logic that Azure Monitor can't express. Could be built incrementally on top of the existing dashboard alert framework (which already has the alarm config UI and inactivity alarm).

---

## Option 5 — Azure App Configuration + Feature Flags

[Azure App Configuration](https://learn.microsoft.com/en-us/azure/azure-app-configuration/overview) is a managed service for centralised configuration. Alert thresholds are stored as key-value pairs and referenced by services at runtime.

```
# Thresholds stored in App Configuration
integration-hub:alerts:queue-warning-threshold = 10
integration-hub:alerts:queue-critical-threshold = 50
integration-hub:alerts:dlq-warning-threshold = 1
integration-hub:alerts:inactivity-minutes = 30
```

Services (including the alert container or dashboard) read these at startup or poll for changes. Support staff update values in the portal — no deployment required, changes are picked up within the poll interval.

**Key feature:** App Configuration supports **labels** (e.g., `production`, `staging`, `dr-west`) so DR environments can have different thresholds without separate config stores.

### Pros
- Managed service — no database to maintain
- Native Azure RBAC: support staff get config read/write, not infrastructure write
- Full change history and point-in-time restore built in
- Integration with Azure Key Vault for any secrets mixed with config
- Supports feature flags (e.g., "enable ChemoCare alerting") — useful during go-live

### Cons
- Another service dependency
- Soft limit of 10,000 key-values on the free tier; paid tier needed for production
- Not a complete solution on its own — still need alert evaluation logic somewhere

**Verdict:** Excellent complement to any of the above options. Recommended as the config store for Option 3 or 4 if a lightweight solution is acceptable, rather than building a custom DB schema.

---

## Option 6 — GitOps (Config-as-Code with PR Workflow)

Support staff do not directly edit Azure — instead they raise a pull request to the repository with updated threshold values. A pipeline applies the change via Terraform (or a lightweight config-only apply).

```
Support staff raises PR: queue_warning_threshold = 15
          ↓
Team lead approves (2-minute review)
          ↓
Pipeline applies config change to Azure App Configuration or Terraform
          ↓
Change is live within minutes
```

### Pros
- Full audit trail in Git — every change has a PR, reviewer, and comment
- Changes are reviewed before they go live — prevents accidental misconfigurations
- Rollback is a revert commit
- No new infrastructure

### Cons
- Requires support staff to be comfortable with Git and PRs
- Adds latency — a change is not immediate, it requires a human approval step
- May not be fast enough for incident response (support staff need to lower a threshold *now*)
- Cultural overhead: some teams resist putting operational config into code review

**Verdict:** Good for planned threshold changes and governance. Too slow for incident response. Best combined with an escape hatch (Option 5 for emergency overrides).

---

## Disaster Recovery Considerations

When the primary Azure region (e.g., UK South) becomes unavailable and workloads fail over to the secondary region (e.g., UK West), alert configuration must follow.

### The problem

Azure Monitor alert rules are scoped to a specific region and resource group. If you fail over to UK West:
- Alert rules in UK South still exist but monitor resources that no longer exist
- Alert rules in UK West don't exist unless explicitly provisioned
- Support staff may have tuned UK South thresholds that are now lost

### Approaches

#### DR approach A — Active-Active alert rules (Terraform)

Terraform provisions identical alert rules in both regions. During normal operation, UK West alerts are suppressed via Alert Processing Rules. On failover, the suppression rule is removed (or disabled via the config service).

```hcl
# Same alert rule in both regions
module "alerts_uk_south" { source = "./modules/alerts"; location = "uksouth" }
module "alerts_uk_west"  { source = "./modules/alerts"; location = "ukwest" }
```

#### DR approach B — Config-driven alert evaluation (preferred)

If using the Alert Container (Option 4) or App Configuration (Option 5), alert thresholds are not tied to a region. The alert evaluator queries the correct Service Bus namespace for the active region, using the same thresholds. Failover is transparent to the alert configuration.

```
App Configuration (geo-replicated) ──→ Alert Container (deployed in both regions)
                                              ↓
                                    Monitors whichever Service Bus is active
```

#### DR approach C — Azure Monitor Backup via ARM templates

Export current alert rule configuration (including any support staff changes) to ARM templates periodically. Store in Azure Blob Storage. On DR failover, apply the ARM templates to the secondary region. This captures drift from portal changes.

```bash
# Export current state
az monitor metrics alert list --resource-group rg-ih-uksouth --output json > alerts-backup.json

# Restore in DR region
az deployment group create --resource-group rg-ih-ukwest --template-file alerts-backup.json
```

### DR Checklist for Alerts

- [ ] Alert rules exist in secondary region (or are config-driven, not region-bound)
- [ ] Action Groups are replicated (they are global resources in Azure, but verify)
- [ ] Suppression rules for secondary region are pre-configured (not active until failover)
- [ ] Alert thresholds for DR may differ (e.g., higher tolerance during switchover)
- [ ] NOC dashboard connects to secondary region Service Bus on failover
- [ ] Runbook documents how to activate DR alerting

---

## Best Practices Summary

### Separate structure from values

| Terraform owns | Support staff own |
|----------------|-------------------|
| Alert rule names and types | Threshold values |
| Metric targets (queue names) | Severity levels |
| Action Group definitions | Notification recipients |
| Resource scopes | Suppression windows |

### Audit everything

Every threshold change should record: who, when, old value, new value, reason. Either use App Configuration's built-in history, Git history via GitOps, or a custom audit table in the config service DB.

### Test before applying

Before lowering a DLQ threshold from 5 to 1 in production, run a backtest: "how many times would this threshold have fired in the last 7 days?" A config service UI can surface this automatically using Log Analytics.

### Alert on the alerting system

Your alerting infrastructure should itself be monitored:
- Alert if no alerts have fired in 48 hours (possible misconfiguration)
- Alert if the alert container / config service is down
- Regular "canary" test: send a known-bad message and verify an alert fires

### Avoid alert fatigue

- Use dynamic thresholds for volume-based metrics
- Implement alert correlation (multiple DLQ hits on the same flow = one alert, not five)
- Distinguish between "information" (queue backing up), "warning" (threshold crossed), and "critical" (messages being lost or service down)
- Business-hours suppression for non-critical alerts

### Consider the support staff experience

Whatever solution is chosen, the support staff interface should be:
1. **Accessible** — no Azure portal access required; the NOC dashboard can host it
2. **Safe** — validation before saving (is this threshold sane? will it cause storms?)
3. **Audited** — who changed what, with a comment field
4. **Reversible** — one-click rollback to previous values

---

## Recommended Approach for Integration Hub

Given the current state and team size, a phased approach is recommended:

### Phase 1 — Immediate (1–2 days)
Add `lifecycle { ignore_changes }` to alert threshold properties in Terraform. This stops deployments from resetting support staff changes immediately, with zero new infrastructure.

### Phase 2 — Short term (1–2 sprints)
Move alert thresholds to **Azure App Configuration**. The dashboard (and future alert container) reads thresholds from App Configuration. Terraform provisions the App Configuration resource and sets initial values; ongoing changes are made via the portal or a simple admin page in the NOC dashboard.

### Phase 3 — Medium term (future sprint)
Extend the existing dashboard alarm framework into a full **Alert Container** with:
- Schedule-based evaluation of queue depths, exception rates, inactivity
- Config DB (App Configuration) for thresholds
- Audit log of all changes
- Backtest UI: "how often would this threshold have fired last week?"
- DR-aware: evaluates whichever region's Service Bus is active

### Phase 4 — DR readiness
Provision alert rules (or the alert container) in the secondary region. Store thresholds in geo-replicated App Configuration. Document and test the DR failover runbook for alerting.

---

## Decision Matrix

| Option | Effort | Operational simplicity | Audit trail | DR-ready | Recommended for |
|--------|--------|----------------------|-------------|----------|-----------------|
| `ignore_changes` | Very low | ✅ Simple | ❌ Portal only | ❌ No | Immediate fix |
| Azure Alert Processing Rules | Low | ✅ Simple | ✅ Activity log | ⚠️ Partial | Suppression/routing |
| Azure App Configuration | Medium | ✅ Simple | ✅ Built-in | ✅ Geo-replicated | Threshold store |
| Config in NOC Dashboard | Medium | ✅ Best UX | ✅ Custom | ✅ Yes | Long-term UI |
| Alert Container | High | ✅ Full control | ✅ Custom | ✅ Yes | Complex logic |
| GitOps | Low | ⚠️ Requires Git | ✅ Git history | ✅ Yes | Governance overlay |
| Dynamic thresholds | Low | ✅ Self-tuning | ⚠️ Limited | ✅ Yes | Volume metrics |
