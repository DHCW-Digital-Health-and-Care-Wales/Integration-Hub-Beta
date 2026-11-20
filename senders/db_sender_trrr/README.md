# TRRR Database Sender (`db_sender_trrr`)

## Overview

`db_sender_trrr` writes TRRR identifier requests to a health board's `Clinical_Results` database. It does **no HL7
parsing or mapping**: that is done upstream by [`lims_trrr_mapper`](../../transformers/lims_trrr_mapper/README.md),
which publishes one JSON request per mapped HL7 message to the mapped topic.

```text
LIMS topic ──► lims_trrr_mapper (NHS_ID_UPDATE) ──┐
           └─► lims_trrr_mapper (MERGE) ──────────┴─► mapped topic ──► 6 x db_sender_trrr (one per health board)
```

Each instance subscribes to the mapped topic with its board's subscription, which has no filter, so every
board receives every request. The sender identifies the request type from the JSON body: a body containing
`OldIdentifier` is a merge, anything else is an NHS-ID update. It then validates the body against that type
and calls the stored procedure.

### Request types

Both request types call the same procedure, `dbo.spProcessResult`, with positional parameters:

| Request type | JSON fields (parameter order) | Parameters |
| --- | --- | --- |
| `NHS_ID_UPDATE` | `LIMSIdentifier`, `NewIdentifier`, `NewIdentifierAssigningAuthority` | 3 |
| `MERGE` | `OldIdentifier`, `OldIdentifierAssigningAuthority`, `NewIdentifier`, `NewIdentifierAssigningAuthority` | 4 |

The JSON fields are passed exactly as received (no numeric coercion). An individual field may be an empty string
when the mapper could not map it; it is passed through as blank.

### Failure handling

| Situation | Outcome |
| --- | --- |
| Body is not JSON, not an object, has missing/non-string fields, mixes fields of both request types, or every field is blank | Dead-lettered `InvalidPayload`, no database call |
| Non-recoverable database error | Dead-lettered `StoredProcedureExecutionFailed` |
| Transient database error / unexpected error | Abandoned for redelivery |

Logs and events never contain the payload (it holds the NHS number). They use the `MessageControlId` and
`MessageType` application properties stamped by the mapper (logged as `UNKNOWN` if absent; they are not
needed to process the request).

## Required environment variables

- `SERVICE_BUS_CONNECTION_STRING`
- `SERVICE_BUS_NAMESPACE`
- `INGRESS_TOPIC_NAME` (the mapped topic, e.g. `local-inthub-lims-trrr-mapped`)
- `INGRESS_SUBSCRIPTION_NAME`
- `INGRESS_SESSION_ID` (must equal the mappers' `EGRESS_SESSION_ID`, `lims-trrr-mapped`)
- `DB_SERVER` (default `TES06SRVSQLNOD1`)
- `DB_NAME` (default `Clinical_Results`)
- `DB_USERNAME` (default `TRRR`)
- `DB_PASSWORD` (default `trrr`)
- `DB_STORED_PROCEDURE` (default `dbo.spProcessResult`, used for both request types)
- `WORKFLOW_ID`
- `MICROSERVICE_ID`

## Default database target

```text
jdbc:sqlserver://TES06SRVSQLNOD1;databaseName=Clinical_Results
user: TRRR
password: trrr
```

The service preserves identifier formatting exactly as received and does not coerce values to numeric types.
