# In-App Replay — Design Note

## Goal

Allow an operator to trigger replay of a `ReplayBatchId` directly from the
`replay_browser` UI, instead of having to run the standalone
`message_replay_job` container manually with `REPLAY_BATCH_ID` set.

The current split is:

| Step | Component | Where |
|---|---|---|
| 1. Select messages + enqueue rows into `monitoring.MessageReplayQueue` (`Status='Pending'`) | `replay_browser` | `replay_create` route |
| 2. Read pending rows for a batch, send them to the priority Service Bus queue, mark as `Loaded` (or `Failed`) | `message_replay_job` | One-shot Container Apps Job |

The browser owns step 1; step 2 is what we want a button to trigger.

---

## Existing code that already does the work

All in `message_replay_job/`:

- `message_replay_job.py` — `MessageReplayJob.run()` loops batches of
  `REPLAY_BATCH_SIZE` rows, sends via `MessageSenderClient.send_message_batch`,
  flips status to `Loaded`. Retry / timeout / oversize-message semantics are
  non-trivial — see `_send_to_service_bus_with_retry`.
- `db_client.py` — `DatabaseClient` (persistent pyodbc connection,
  reconnect-on-failure, MSI or SQL auth).
- `replay_record.py`, `replay_status.py` — value types.
- `app_config.py` — env-var loader, validates `REPLAY_BATCH_ID` is a UUID and
  `REPLAY_BATCH_SIZE` is a positive int.

We should **reuse** these, not reimplement.

---

## Design options

### Option A — Run synchronously inside the Flask request

`POST /replay/queue/run` builds an `AppConfig` and calls
`MessageReplayJob(config).run()` before returning the response.

| Pros | Cons |
|---|---|
| Smallest code change | Blocks a gunicorn worker for the entire batch (minutes for thousands of messages) |
| User sees the final outcome directly | Hits HTTP / load-balancer / Container Apps ingress timeouts |
| No new infra | No progress feedback; second click re-runs the same batch |
| | Forces the browser image to ship Service Bus dependencies and RBAC |

Only acceptable for **very small batches** (tens of messages).

### Option B — Background thread in the Flask process

Spawn a thread per click; return immediately; UI polls
`monitoring.MessageReplayQueue` to render progress.

| Pros | Cons |
|---|---|
| Returns immediately | Conflicts with the project rule in `AGENTS.md`: *"Do not introduce thread pools or asynchronous request handling for message processing unless explicitly requested."* |
| Reuses the existing job class as-is | Work is lost on container restart / scale-in |
| | Need an in-process lock to stop concurrent runs of the same batch |
| | Multiple gunicorn workers means the lock has to be in the DB anyway |

Not recommended without an explicit exception to the rule.

### Option C — Trigger the existing `message_replay_job` Container Apps Job from the UI **(recommended)**

`POST /replay/queue/run` calls the Azure management API to start a one-off
execution of the existing job, passing `REPLAY_BATCH_ID=<uuid>` as an env-var
override.

```python
from azure.identity import DefaultAzureCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient

client = ContainerAppsAPIClient(DefaultAzureCredential(), subscription_id)
client.jobs.begin_start(
    resource_group_name=rg,
    job_name="message-replay-job",
    template={
        "containers": [{
            "name": "message-replay-job",
            "env": [{"name": "REPLAY_BATCH_ID", "value": batch_id}],
        }]
    },
)
```

| Pros | Cons |
|---|---|
| Reuses the existing, tested job | Needs the Azure Container Apps SDK in the browser image |
| Preserves the no-async-in-handler rule | New RBAC role on the browser's managed identity (*Container Apps Jobs Operator* on the job resource) |
| Isolation — a slow / failing replay can't take the browser down | Slightly more infra plumbing (Terraform changes) |
| Container Apps Jobs already handle retries, logs, timeouts | Status comes back via polling `MessageReplayQueue`, not the HTTP response |
| Works the same in DEV / TST / PRD | |

This is the option I'd build.

---

## Recommended implementation (Option C)

### 1. Configuration — `replay_browser/config.py`

Add:

| Env var | Notes |
|---|---|
| `AZURE_SUBSCRIPTION_ID` | Where the job lives |
| `AZURE_RESOURCE_GROUP` | RG of the Container Apps environment |
| `REPLAY_JOB_NAME` | Default: `message-replay-job` |
| `MANAGED_IDENTITY_CLIENT_ID` | Already used elsewhere; reused for `DefaultAzureCredential` |

No Service Bus config is needed in the browser — the job container already has
it.

### 2. New module — `replay_browser/replay_trigger.py`

Thin wrapper around `ContainerAppsAPIClient.jobs.begin_start`. One public
function:

```python
def start_replay_job(batch_id: str) -> str:
    """Start a replay job execution for the given batch. Returns the execution name."""
```

Responsibilities:
- Validate `batch_id` is a UUID (reuse the same check as
  `message_replay_job.app_config._validate_uuid`).
- Build the env-var override (`REPLAY_BATCH_ID=<batch_id>`).
- Call `begin_start(...)` and return the polling result's execution name so the
  UI can show / link to it.

Lazy-import the Azure SDK inside the function to keep unit tests independent of
the SDK install (matches the existing `pyodbc` pattern in `db_client.py`).

### 3. New repository helper — `replay_browser/db_client.py`

Add `get_batch_run_status(batch_id) -> ReplayBatchRunStatus` that aggregates:

```sql
SELECT
  SUM(CASE WHEN Status = 'Pending' THEN 1 ELSE 0 END) AS pending,
  SUM(CASE WHEN Status = 'Loaded'  THEN 1 ELSE 0 END) AS loaded,
  SUM(CASE WHEN Status = 'Failed'  THEN 1 ELSE 0 END) AS failed,
  MAX(ProcessedAt) AS last_processed_at
FROM monitoring.MessageReplayQueue
WHERE ReplayBatchId = ?;
```

Used both by the result page and by the queue screen to colour-code each batch.

### 4. New routes — `replay_browser/app.py`

```
POST /replay/queue/run          form: batch_id -> triggers job, redirects to /replay/queue/run/<batch_id>
GET  /replay/queue/run/<batch>  shows progress (pending / loaded / failed counts); auto-refresh every 5s
```

The POST handler must reject the click if any rows for that batch are still
`Pending` from a previous run (i.e. a run is already in flight). This is the
DB-level lock that replaces an in-process mutex.

### 5. UI — `replay_queue.html`

Add a "Run batch" button per `ReplayBatchSummary` row. Disable / hide it when
`pending == 0` (nothing to do) or when a run is already in flight for that
batch.

### 6. Terraform

In `Integration-Hub-Terraform/components/app-platform` (or wherever the browser
managed identity is defined):

- Grant the browser identity *Container Apps Jobs Operator* scoped to the
  `message-replay-job` resource — **not** the whole resource group.
- No new Service Bus role needed (the browser doesn't send messages itself).

This is a privileged change — needs human review per the repo's
`copilot-instructions.md`.

### 7. Pipelines

No changes. The job is already deployed; we're just calling its start API.

---

## Concurrency / idempotency

The job itself is safe to run concurrently against the same batch (`READPAST`,
status flip is atomic per row). The risk is operator confusion, not data
corruption. Guard at the UI/handler layer:

1. Before starting, count `Pending` rows for the batch. If zero, nothing to do
   — return early.
2. Optionally, persist a `monitoring.ReplayBatchRun` row (`BatchId`,
   `StartedAt`, `StartedBy`, `ExecutionName`, `FinishedAt`) so the UI can show
   history and refuse a second click while `FinishedAt IS NULL`. Updating
   `FinishedAt` would be done by a small polling endpoint, or left to a future
   iteration.

For an MVP, the pending-row count check is enough.

---

## Testing

- Unit tests for `replay_trigger.start_replay_job` with the Azure SDK mocked.
- Unit tests for the new route — assert it rejects non-UUID input, rejects when
  no pending rows, and calls `start_replay_job` with the right batch id.
- Unit test for `get_batch_run_status` against a fake `pyodbc` cursor (matches
  existing patterns in the repo).
- Manual smoke test in DEV: enqueue 5 messages, click *Run batch*, watch
  counts move from `Pending` → `Loaded`.

---

## Open questions

1. **Audit trail** — do we want `StartedBy` (operator AD identity) recorded
   against each run? The browser already runs behind AAD auth; capturing
   `X-MS-CLIENT-PRINCIPAL-NAME` is straightforward.
2. **Cancellation** — Container Apps Jobs supports `begin_stop_execution`. Do
   we expose a *Cancel* button, or out-of-scope for v1?
3. **Result visibility** — is polling the DB enough, or do we also want a link
   straight into the Container Apps Job execution logs in the portal?
