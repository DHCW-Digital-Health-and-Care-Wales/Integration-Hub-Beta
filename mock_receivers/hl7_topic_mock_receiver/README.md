# HL7 MLLP Topic Mock Receiver

Configurable HL7 MLLP server built with hl7apy package used for testing. Identical MLLP/ACK
behaviour to the sibling [hl7_mock_receiver](../hl7_mock_receiver), but forwards every accepted
message to a Service Bus **topic** instead of a queue, so multiple independent subscriptions can
consume the same verified traffic.

Accepted message types:

- "ADT^A31^ADT_A05"
- "ADT^A28^ADT_A05"
- "ADT^A40^ADT_A39"

A negative ack can be produced by having a keyword inside the message body:

- `fail` - produces an `AE` (Application Error) ack.
- `reject` - produces an `AR` (Application Reject) ack.

Note: interpretation of the `AE`/`AR` ack codes (e.g. retry vs. dead-letter) is up to the
receiving sender - this mock receiver only controls which ack code is returned.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_topic_mock_receiver](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit -r hl7_topic_mock_receiver/ tests/
uv run mypy --ignore-missing-imports hl7_topic_mock_receiver/ tests/
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Running HL7 server

You can run the HL7 server directly with uv or build docker image and run it in the container.
To define host and port the server should bind to use environment variables configuration.

### Environment variables

- **HOST** - default 127.0.0.1
- **PORT** - default 2576
- **LOG_LEVEL** - default 'INFO'
- **EGRESS_TOPIC_NAME** - Service Bus topic to publish accepted messages to (optional - if unset,
  messages are still ACKed but not forwarded)
- **EGRESS_SESSION_ID** - session id used when publishing (required by the topic's
  `requires_session` setting)
- **SERVICE_BUS_CONNECTION_STRING** / **SERVICE_BUS_NAMESPACE** - Service Bus connectivity
  (connection string for local/emulator use, namespace for RBAC/managed identity in cloud
  environments)
- **HEALTH_CHECK_HOST** - default 127.0.0.1
- **HEALTH_CHECK_PORT** - default 9000

### Running directly

From the [hl7_topic_mock_receiver](.) folder run:

```bash
python application.py
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
