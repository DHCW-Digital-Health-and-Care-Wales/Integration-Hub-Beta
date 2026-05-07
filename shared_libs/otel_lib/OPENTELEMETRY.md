# OpenTelemetry in the Integration Hub

## What problem does this solve?

Before this change, the NOC dashboard could show you *that* something was wrong
(queue depth rising, exceptions appearing) but couldn't tell you *what happened to a
specific message*. If a patient record ended up in the dead-letter queue, there was no
way to follow its journey and find exactly where and why it failed.

OpenTelemetry gives every message a **trace** — a chain of timestamped records (called
**spans**) that follows the message from entry to delivery. Each service adds its own
span, and they all link together using a common trace ID so you can see the full
end-to-end picture in one view inside Application Insights.

---

## How a message is traced

A typical PHW → MPI message travels through five hops. With OTel, each hop creates a
span and they are all stitched together by a shared trace ID:

```
PHW System
    │
    ▼
[Span 1]  hl7-server         receives MLLP message, enqueues to pre-queue
    │       duration: 4 ms    attributes: queue=pre-phw-transform
    │
    │  traceparent header travels inside the Service Bus message
    ▼
[Span 2]  phw-hl7-transformer dequeues, transforms, enqueues to post-queue
    │       duration: 18 ms   attributes: queue=post-phw-transform
    │
    │  traceparent header travels inside the Service Bus message
    ▼
[Span 3]  hl7-sender          dequeues, sends to MPI
            duration: 31 ms   attributes: queue=post-phw-transform
```

All three spans share the same `trace_id`. In App Insights you can search by that ID
and see the full chain with timings for each step.

---

## What was built

### `shared_libs/otel_lib/` — new shared library

The central piece. Every service that wants tracing imports from here.

**`configure_otel(service_name)`**
Call this once at service startup. It:
1. Reads `APPLICATIONINSIGHTS_CONNECTION_STRING` from the environment
2. If present — configures the Azure Monitor exporter so spans go to App Insights
3. If absent — installs a silent no-op provider so the service starts cleanly with
   no telemetry output and no errors. Nothing breaks if the env var isn't set.
4. Installs `OtelCorrelationFilter` on the Python root logger so every log line
   automatically carries the current `trace_id` and `span_id` as extra fields

**`inject_trace_context(properties: dict) → dict`**
Adds W3C `traceparent` and `tracestate` headers to a dict. Used when sending a
Service Bus message — the context is embedded in the message's `application_properties`
so the next service can pick it up.

**`extract_trace_context(properties: dict) → Context`**
Reads the `traceparent`/`tracestate` from an incoming message's `application_properties`
and reconstructs the remote trace context. Used when receiving a message so the new
span is linked to the upstream span as a child, not created as an orphan.

**`get_tracer(name) → Tracer`**
Returns an OTel `Tracer` for the given module name. Use this to create custom spans
for specific operations if needed.

**`OtelCorrelationFilter`**
A Python `logging.Filter` subclass. When attached to the root logger it adds two
fields to every log record:
- `otel_trace_id` — 32 hex characters, e.g. `4bf92f3577b34da6a3ce929d0e0e4736`
- `otel_span_id` — 16 hex characters, e.g. `00f067aa0ba902b7`

These fields appear in Application Insights logs, allowing you to correlate a log
line with the exact span it was emitted under.

---

### `shared_libs/message_bus_lib/` — trace context propagation

**Sending** (`MessageSenderClient.send_message`):
Before building the `ServiceBusMessage`, the sender calls `inject_trace_context()`
and merges the result into `application_properties`. The `traceparent` header is now
carried inside the message envelope — invisible to the HL7 payload.

**Receiving** (`MessageReceiverClient._invoke_with_trace_context`):
Before calling the user's message handler, the receiver calls `extract_trace_context()`
on the message's `application_properties` and attaches the resulting context to the
current thread using `otel_context.attach()`. This means any span created inside the
handler is automatically a child of the upstream span. The context is detached cleanly
in a `finally` block whether the handler succeeds or raises.

Both behaviours are controlled by `propagate_trace_context=True` (the default). Setting
it to `False` skips all OTel work — existing callers that don't pass this argument are
unaffected.

If `otel_lib` is not installed at all, the code catches `ImportError` and continues
without tracing. The Service Bus library has no hard dependency on `otel_lib`.

---

### `shared_libs/processor_manager_lib/` — span wrapping

**`ProcessorManager.wrap_handler(handler, service_name, queue_name)`**
Wraps any message handler function in an OTel span. The span:
- Is named `"{service_name}.process_message"` (e.g. `phw-hl7-transformer.process_message`)
- Carries standard OpenTelemetry messaging attributes:
  - `messaging.system = "azure_service_bus"`
  - `messaging.destination` = the queue name
  - `messaging.message_id` = the message ID if available
- On exception: calls `span.record_exception(exc)` and sets the span status to `ERROR`
  before re-raising. This means failed messages are immediately visible in the
  App Insights failures view.
- If OTel is not configured (no-op provider installed), `wrap_handler` returns the
  original handler unchanged — zero overhead.

---

### `shared_libs/event_logger_lib/` — log correlation

The existing `event_logger_lib` sends structured log events to Application Insights as
custom events. It now enriches each event with:
- `otel_trace_id` — from the active span at the time of logging
- `otel_span_id` — from the active span at the time of logging

This means you can click a log event in App Insights and immediately jump to the
associated trace, or vice versa.

---

### `hl7_phw_transformer/` — pilot instrumentation

The PHW transformer is the first (and currently only) service with OTel enabled.
`configure_otel("phw-hl7-transformer")` is called at startup.

All other services (`hl7_chemo_transformer`, `hl7_pims_transformer`, `hl7_sender`,
`hl7_server`) have a `# TODO: add configure_otel() call once otel_lib is validated`
comment in their startup code. Rolling them out is a one-liner each.

---

## What you see in Application Insights

Once deployed, Application Insights will show:

| View | What you get |
|------|-------------|
| **Transaction search** | Search by trace ID to see every span for a single message journey |
| **Application map** | Automatic service dependency diagram built from real traffic |
| **Performance** | Per-operation latency percentiles (e.g. how long does `phw-hl7-transformer.process_message` take at P95?) |
| **Failures** | Failed spans grouped by exception type, linked to the log and the full trace |
| **Logs** | Every log line tagged with `otel_trace_id` / `otel_span_id` for instant correlation |

---

## Rolling out to remaining services

For each service that still has the `# TODO` comment:

1. Add `otel-lib` to its `pyproject.toml`:
   ```toml
   [project]
   dependencies = [
     ...
     "otel-lib",
   ]

   [tool.uv.sources]
   otel-lib = { path = "../shared_libs/otel_lib" }
   ```

2. Run `uv lock` in that service directory.

3. Add one call at the top of `application.py` / `app.py`:
   ```python
   from otel_lib import configure_otel
   configure_otel("chemo-hl7-transformer")  # use the Container App name
   ```

4. Wrap the message handler:
   ```python
   from processor_manager_lib import ProcessorManager
   manager = ProcessorManager()
   instrumented_handler = manager.wrap_handler(
       my_handler, "chemo-hl7-transformer", queue_name
   )
   ```

No other changes are needed. The `message_bus_lib` propagation is already active.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | If set, spans are exported to Azure Monitor. If absent, tracing is silent. |

The connection string is already used by `event_logger_lib` for log export — the same
value is reused. No new secrets are needed.
