# Dashboard — To Do

## ~~Scale: 200+ flows~~ ✅ Done

**Overview page**: Flow cards replaced with a compact table — one row per flow with status dot, name (links to detail), route, active count, DLQ count, and health badge. Scales to any number of flows.

**Flows page**: Flows grouped by source system with collapsible sections. Group headers show system name, worst health, and rolled-up active/DLQ counts. Warning/critical groups auto-expand; healthy groups start collapsed. Collapse/expand state persists in `sessionStorage`. Search auto-expands matching groups.

## ~~Recent Exceptions panel~~ ✅ Done

## OpenTelemetry — distributed message tracing

**Problem:** The dashboard shows queue depths and exception counts but can't answer "what happened to a specific HL7 message?" When something goes wrong there's no way to trace a message across its full journey or link a DLQ entry back to the exact processing step that failed.

**Approach:** Instrument the Python services with the Azure Monitor OpenTelemetry distro and propagate trace context through Service Bus messages. No new infrastructure needed — Azure Monitor already accepts OTLP and exports to App Insights.

### Service-side work (do first)

1. Add `azure-monitor-opentelemetry` to each service's `pyproject.toml`
2. Initialise the OTel SDK at startup (one call: `configure_azure_monitor()`)
3. Wrap each message handler in a span — name it after the flow + operation (e.g. `phw-transformer.process`)
4. Propagate `traceparent` as a Service Bus message application property when enqueuing, and extract it when dequeuing — this chains spans across queue hops
5. Extend `event_logger_lib` to attach the current `trace_id` / `span_id` to every log record

### Dashboard work (follow-on)

- Add a "trace" link on exception table rows (construct App Insights deep-link from `operation_Id`)
- Add trace ID column to the messages page
- Consider a message detail drilldown: given a trace ID, show all spans end-to-end (HL7 Server → pre-queue → Transformer → post-queue → Sender → MPI) with per-hop latency

### Notes
- The Service Bus SDK has built-in OTel instrumentation (`opentelemetry-instrumentation-azure-servicebus`) — use it rather than manual span creation around SDK calls
- `traceparent` header format is W3C standard — just pass it through as a message property
- Existing `event_logger_lib` custom events and App Insights exceptions are unaffected; OTel adds traces alongside them
- Start with one flow (e.g. PHW → MPI) as a pilot before rolling out to all services

