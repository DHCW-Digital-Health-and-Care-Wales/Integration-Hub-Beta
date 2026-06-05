# Replay Browser

Flask web application for browsing messages stored in `monitoring.Message`, viewing a selected
message in a structured HL7 layout, and queuing messages for replay.

## Run locally

```bash
uv sync
uv run flask --app replay_browser.app:create_app run --debug
```

By default, the app reads SQL connection settings from environment variables:

- `SQL_SERVER` (default: `localhost,1433`)
- `SQL_DATABASE` (default: `IntegrationHub`)
- `SQL_USERNAME` (default: `sa`)
- `MSSQL_SA_PASSWORD` (required when username is set)
- `SQL_ENCRYPT` (default: `No`)
- `SQL_TRUST_SERVER_CERTIFICATE` (default: `Yes`)
- `MESSAGE_BROWSER_PAGE_SIZE` (default: `30`)

## Endpoints

- `GET /messages` - paginated message list
- `GET /messages/<id>` - message details + structured HL7 view
- `POST /replay/review` - review/edit a set of messages before queueing a replay batch
- `POST /replay/create` - enqueue the chosen messages as a new batch, or add them to an existing one
- `GET /replay/queue` - view the replay queue, filterable by batch reference and sortable by column
- `POST /replay/queue/remove` - remove selected entries from their batch

## List filters

`/messages` supports these query parameters:

- `q` - free-text search across correlation id, source system, and raw payload
- `destination` - filter by destination (`TargetSystem`)
- `start_date` - inclusive lower bound for `ReceivedAt` (`YYYY-MM-DD`)
- `end_date` - inclusive upper bound for `ReceivedAt` (`YYYY-MM-DD`)
- `sort_by` - `id` or `received_at`
- `sort_dir` - `asc` or `desc`

## Replaying messages

The browser can queue stored messages for replay; it does **not** publish them itself. It writes rows
into `monitoring.MessageReplayQueue` (status `Pending`), and the separate `message_replay_job` service
reads that queue and republishes the messages to Service Bus.

Two selection modes are offered from the message list:

- **Replay selected** - tick the per-row checkboxes and submit only those messages.
- **Replay all matching filters** - replay every message matching the current `q`, `destination`, and
  date-range filters (not just the current page).

Flow:

1. From `/messages`, choose a selection mode. This POSTs to `/replay/review`.
2. The review screen lists the chosen messages with per-row "keep" checkboxes so you can drop any you
   do not want. Each row links to its detail view for inspection.
3. Submitting the review POSTs to `/replay/create`. You can either:
   - **Create new batch** - inserts the kept message ids under a fresh `ReplayBatchId` (a UUID), or
   - **Add to existing batch** - supply an existing batch id to append the messages to that batch.
     Adding is idempotent: messages already in the batch are skipped.
4. To actually publish the batch, hand the batch id to `message_replay_job` (set `REPLAY_BATCH_ID`),
   point the consuming sender's `INGRESS_QUEUE_NAME` at the priority queue, run the replay job, then
   revert the sender configuration.

### Managing the replay queue

The **Replay Queue** screen (`/replay/queue`, linked from the top navigation) lists every row in
`monitoring.MessageReplayQueue`, enriched with each message's correlation id, source, and destination.

- **Filter by batch reference** - the `batch` query parameter matches a full or partial `ReplayBatchId`.
  Batch chips at the top give a one-click filter and show pending/total counts.
- **Sort** - `sort_by` is one of `replay_id`, `batch_id`, `message_id`, `status`, `created_at`, with
  `sort_dir` of `asc` or `desc` (column headers toggle this).
- **Remove from a batch** - tick rows and submit to `/replay/queue/remove`. This deletes only the queue
  entry (by `ReplayId`); the original row in `monitoring.Message` is left untouched.
