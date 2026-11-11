# TRRR Database Sender (`db_sender_trrr`)

## Overview

`db_sender_trrr` is a TRRR-specific database sender that mirrors the generic `db_sender` pattern while enforcing the LIMS/NHS identifier mapping for ADT_A05 messages.

It selects the ID values from `PID-3` by assigning authority:

- `328` -> `LIMSIdentifier`
- `NHS` -> `NewIdentifier`

The mapped values are then passed as a structured update request to the database layer only when both values are present. If either identifier is missing, the message is rejected and no database update request is created.

### Mapping types and routing

Routing is done upstream by separate Service Bus subscriptions; each `db_sender_trrr` instance applies the one mapping selected by `TRRR_MAPPING_TYPE` and never infers it from message content:

| `TRRR_MAPPING_TYPE` | Upstream subscription | Accepts | Default procedure |
| --- | --- | --- | --- |
| `NHS_ID_UPDATE` (default) | A31 NHS-IDUpdate and A40 NHS-IDUpdate (`PID-3.4.1` = LIMS authority and `NHS`) | `A31`, `A40` | `dbo.TRRRIDUpdate` |
| `MERGE` | A40 Merge (every `MSH-9.2` = `A40`) | `A40` | `dbo.TRRRIDMerge` |

An `A40` is delivered to both subscriptions, so both instances process it and two TRRR requests result.

The sender does no routing of its own: every message that arrives is mapped. Subscription filters cannot inspect HL7 body fields, so a message the instance cannot map (unsupported `MSH-9.2`, or for `NHS_ID_UPDATE` no `PID-3` repetition for the LIMS authority or for `NHS`) is dead-lettered with `MappingFailed` and the reason. For example, an `A40` with no `NHS` identifier is dead-lettered by `NHS_ID_UPDATE` but still processed by `MERGE`.

### ADT^A40 NHS-IDUpdate (`NHS_ID_UPDATE`)

The LIMS identifier is the `PID-3` repetition whose assigning authority equals `MSH-3.1`; the NHS number is the `PID-3` repetition with authority `NHS`. `NewIdentifierAssigningAuthority` is `NHS`; `Old*` fields are not mapped (any `MRG` is ignored). `Missing LIMS identifier`, `Missing NHS identifier` and `Missing sending LIMS authority` (empty `MSH-3.1`) are all dead-lettered.

### ADT^A40 patient merge (`MERGE`)

Every `ADT^A40` handled by a `MERGE` instance is mapped as a patient merge:

| Target field | Source | Rule |
| --- | --- | --- |
| `OldIdentifier` | `MRG-1.1` | Copied as received |
| `OldIdentifierAssigningAuthority` | `MRG-1.4.1` | Copied as received |
| `NewIdentifier` | `PID-3.1` | The repetition whose `PID-3.4.1` equals `MRG-1.4.1` |
| `NewIdentifierAssigningAuthority` | `PID-3.4.1` | The authority matching `MRG-1.4.1` |
| `LIMSIdentifier` | - | Not mapped |

Messages are dead-lettered (reason `MappingFailed`, no database call) with `Missing old identifier`, `Missing old assigning authority` or `Missing new identifier`. The merge request is sent to `DB_STORED_PROCEDURE` (default `dbo.TRRRIDMerge` for `MERGE`) as `(OldIdentifier, OldIdentifierAssigningAuthority, NewIdentifier, NewIdentifierAssigningAuthority)`.

## Required environment variables

- `SERVICE_BUS_CONNECTION_STRING`
- `SERVICE_BUS_NAMESPACE`
- `INGRESS_TOPIC_NAME`
- `INGRESS_SUBSCRIPTION_NAME`
- `DB_SERVER` (default `TES06SRVSQLNOD1`)
- `DB_NAME` (default `Clinical_Results`)
- `DB_USERNAME` (default `TRRR`)
- `DB_PASSWORD` (default `trrr`)
- `TRRR_MAPPING_TYPE` (`NHS_ID_UPDATE` default, or `MERGE`)
- `DB_STORED_PROCEDURE` (default `dbo.TRRRIDUpdate` for `NHS_ID_UPDATE`, `dbo.TRRRIDMerge` for `MERGE`)
- `WORKFLOW_ID`
- `MICROSERVICE_ID`

## Default database target

```text
jdbc:sqlserver://TES06SRVSQLNOD1;databaseName=Clinical_Results
user: TRRR
password: trrr
```

The service preserves identifier formatting exactly as received and does not coerce values to numeric types.
