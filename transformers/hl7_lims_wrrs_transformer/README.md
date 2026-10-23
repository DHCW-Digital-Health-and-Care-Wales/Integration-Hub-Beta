# HL7 LIMS WRRS Transformer

Classifies LIMS ADT `A31`/`A40` messages and publishes one classified message per matching rule to the
classified topic, so the correct WRRS mapping can be applied downstream. It does **not** map or modify the
message body.

## Flow

```
LIMS HL7 input topic ──(LIMS-Wrrs-Transformer subscription)──► lims_wrrs_transformer ──► LIMS-Wrrs-Classified topic
   MessageType IN (A31,A40) AND SourceSystem = 328                     │                   ├─ NhsId sub: MappingType = LIMS_NHS_ID_UPDATE
                                                                       │                   └─ A40 sub:   MappingType = ADT_A40
                                                                       └─ unsupported → dead-lettered
```

## Classification rules

Classification keys on the trigger event (`MSH-9.2`), not the message structure.

| MappingType | Rule |
|---|---|
| `LIMS_NHS_ID_UPDATE` | `MSH-9.2` is `A31` or `A40` **and** `PID-3` (any `PID`, including inside the `ADT_A39` patient group) has identifiers with assigning authority (`CX.4`/`HD.1`) `NHS` **and** `328` |
| `ADT_A40` | `MSH-9.2 = 'A40'` (MRG is not required by the rule; a missing MRG is left for the mapping stage) |

A message can match both rules (e.g. an A40 with NHS and 328 identifiers) and is then published once per rule.
A message matching no rule is dead-lettered with reason **`Unsupported message type`**; an unparseable message is
dead-lettered with reason `Invalid HL7 message`. Both keep the MessageId and correlation ID in the description and logs.

## Output messages

- Body: the inbound HL7 message, unchanged.
- Session ID: `EGRESS_SESSION_ID`.
- Application properties: all inbound properties (correlation ID, workflow ID, `MessageType`, `SourceSystem`,
  trace context, ...) plus:

| Property | Value |
|---|---|
| `MappingType` | The matched rule (contract with the topic subscription filters) |
| `ProcessingId` | New GUID per path |
| `OriginalMessageId` | The inbound Service Bus `message_id` (falls back to `MSH-10`) |

- Service Bus `message_id`: `<original message_id>-<MappingType>`. This is used **only** for duplicate detection.

## Fan-out and partial failure

Each path is sent independently, so a failure on one path does not stop the others. If any path failed the inbound
message is abandoned and redelivered (dead-lettered by Service Bus after the max delivery count). Because the
per-path `message_id` is deterministic, paths that were already published are dropped on redelivery **provided the
classified topic has duplicate detection enabled** (`requires_duplicate_detection = true`; the local emulator
config enables it).

This service has its own processing loop instead of `transformer_base_lib.run_transformer_app`, which is strictly
one message in / one message out. It reuses `TransformerConfig` for the standard environment variables.

## Configuration

Standard transformer variables (`INGRESS_TOPIC_NAME`, `INGRESS_SUBSCRIPTION_NAME`, `INGRESS_SESSION_ID`,
`EGRESS_TOPIC_NAME`, `EGRESS_SESSION_ID`, `WORKFLOW_ID`, `MICROSERVICE_ID`, `SERVICE_BUS_CONNECTION_STRING` or
`SERVICE_BUS_NAMESPACE`, `HEALTH_CHECK_HOST`, `HEALTH_CHECK_PORT`) plus:

| Env var | Purpose | Default |
|---|---|---|
| `MAPPING_TYPE_NHS_ID_UPDATE` | `MappingType` for the LIMS/NHS ID Update rule | `LIMS_NHS_ID_UPDATE` |
| `MAPPING_TYPE_A40` | `MappingType` for the ADT_A40 rule | `ADT_A40` |

Changing the defaults requires matching changes to the Terraform subscription filters. The values must differ.

## Local development

```bash
cd local
docker compose --profile lims-to-mpi up
```

Environment file: `local/env/transformers/lims-wrrs-hl7-transformer.env`.

## Quality checks

```bash
bash check.sh   # ruff, bandit, mypy, unittest
```
