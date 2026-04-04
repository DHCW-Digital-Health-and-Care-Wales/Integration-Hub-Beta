# BusWatch

BusWatch is a small Python web app that peeks Azure Service Bus queue messages and shows message details in a browser.

## Features

- Lists queues from local ServiceBusEmulatorConfig.json (or from configured queue names)
- Shows queue runtime metrics (active, dead-letter, scheduled)
- Peeks messages without dequeueing
- Clears all currently available messages from an individual queue
- Handles session-enabled queues using next available session
- Clickable message sequence numbers to open full message detail
- Message detail supports HL7 structured parsing with per-segment/per-field view (with raw toggle)
- Optional live mode auto-refresh (pause/resume, interval control, and new-row highlight)

## Environment Variables

- `SERVICEBUS_CONNECTION_STRING`: Service Bus connection string. Defaults to emulator-friendly value.
- `BUSWATCH_QUEUE_NAMES`: Optional comma-separated queue names. If omitted, BusWatch loads queue names from `local/ServiceBusEmulatorConfig.json`.
- `BUSWATCH_PEEK_COUNT`: Number of messages to show per queue on the home page. Default: `25`.
- `BUSWATCH_DETAIL_SEARCH_LIMIT`: Max peek depth when searching for a specific sequence number. Default: `250`.

## Run

```bash
cd buswatch
uv sync
uv run uvicorn buswatch.main:app --reload --host 0.0.0.0 --port 8080
```

Then open `http://localhost:8080`.

## Notes

- Message reads use `peek`, so no locks are taken and no messages are removed.
- This project is emulator-first: queue names are read from `local/ServiceBusEmulatorConfig.json` by default.
- Queue runtime counters are not queried from the management API in emulator mode, so those values show as unavailable.
- If the app cannot list queues automatically, set `BUSWATCH_QUEUE_NAMES` explicitly.
- For Docker runs, use `Endpoint=sb://sb-emulator` in `SERVICEBUS_CONNECTION_STRING`.
- Session-enabled queue refreshes are tuned for responsiveness on list pages (short wait, no SDK retries), while detail lookups use a slightly longer wait for stability.

## Troubleshooting

### 1) Connection refused while peeking queues

Error example:

`Message peek failed: Failed to initiate the connection due to exception: [Errno 111] Connection refused`

Common cause:

- BusWatch is running in Docker but `SERVICEBUS_CONNECTION_STRING` uses `Endpoint=sb://localhost`.

Fix:

- In Docker, set `SERVICEBUS_CONNECTION_STRING` to use `Endpoint=sb://sb-emulator`.
- Restart/recreate the BusWatch container after changing env values.

### 2) Session-required queue opened as non-session queue

Error example:

`It is not possible for an entity that requires sessions to create a non-sessionful message receiver`

Common cause:

- BusWatch cannot read queue metadata from `ServiceBusEmulatorConfig.json`, so it cannot detect `RequiresSession=true` queues.

Fix:

- Ensure `ServiceBusEmulatorConfig.json` is mounted into the BusWatch container (for this project: `/app/ServiceBusEmulatorConfig.json`).
- Recreate BusWatch after updating Docker Compose.

### 3) Empty session queue refresh feels slow

Symptoms:

- Refreshing an empty session-enabled queue takes much longer than expected.

Cause:

- Session acquisition (`NEXT_AVAILABLE_SESSION`) can wait while probing for an active session.

Current behavior:

- List refresh uses a short session wait and disabled SDK retries for faster UI response.
- Detail lookup uses a slightly longer session wait to improve reliability.
