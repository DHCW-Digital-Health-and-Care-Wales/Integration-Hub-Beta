# BusWatch

BusWatch is a small Python web app that peeks Azure Service Bus queue messages and shows message details in a browser.

## Features

- Lists queues from a namespace (or from configured queue names)
- Shows queue runtime metrics (active, dead-letter, scheduled)
- Peeks messages without dequeueing
- Clickable message sequence numbers to open full message detail

## Environment Variables

- `SERVICEBUS_CONNECTION_STRING`: Service Bus connection string. Defaults to emulator-friendly value.
- `BUSWATCH_QUEUE_NAMES`: Optional comma-separated queue names. If omitted, BusWatch lists queues from the namespace.
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
- If the app cannot list queues automatically, set `BUSWATCH_QUEUE_NAMES` explicitly.
