# otel-lib

OpenTelemetry distributed tracing library for the NHS Wales Integration Hub.

## Usage

```python
from otel_lib import configure_otel, get_tracer, inject_trace_context, extract_trace_context

# Call once at service startup
configure_otel("my-service-name")

# Create a tracer for a module
tracer = get_tracer(__name__)

# Instrument code with spans
with tracer.start_as_current_span("operation"):
    ...

# Propagate context via Service Bus message properties
props = inject_trace_context({})
# ... attach props to outgoing message ...

# Restore context from incoming message
ctx = extract_trace_context(incoming_props)
```

## Environment Variables

- `APPLICATIONINSIGHTS_CONNECTION_STRING` — Azure Monitor connection string. If absent, a no-op tracer is used.
