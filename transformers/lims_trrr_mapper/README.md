# LIMS TRRR Mapper (`lims_trrr_mapper`)

## Overview

`lims_trrr_mapper` maps LIMS ADT messages to TRRR stored procedure requests. The per-board TRRR database
senders (`senders/db_sender_trrr`) then run those requests and don't do any HL7 mapping of their own.

```text
hl7-soap-server ──► LIMS topic (…-lims-hl7-input)
                      ├─ …-lims-trrr-nhsid-mapper-sub  (A31/A40, SourceSystem 328) ─► mapper NHS_ID_UPDATE ─┐
                      └─ …-lims-trrr-merge-mapper-sub  (A40)                       ─► mapper MERGE        ─┤
                                                                                                           ▼
                                                      TRRR mapped topic (…-lims-trrr-mapped, session lims-trrr-mapped)
                                                      └─ …-trrr-{board}-db-sender-sub (no filter) ─► db_sender_trrr_{board}
```

The same image runs twice. `TRRR_MAPPING_TYPE` selects the mapping. The mappers stay separate because an A40 is
mapped by both, producing an NHS-ID update and a merge request:

| `TRRR_MAPPING_TYPE` | Accepts | Published JSON body (stored procedure parameters) |
| --- | --- | --- |
| `NHS_ID_UPDATE` | `A31`, `A40` | `LIMSIdentifier`, `NewIdentifier`, `NewIdentifierAssigningAuthority` |
| `MERGE` | `A40` | `OldIdentifier`, `OldIdentifierAssigningAuthority`, `NewIdentifier`, `NewIdentifierAssigningAuthority` |

The mapping rules are the ones that used to live in the sender:

- **A31:** the LIMS identifier has authority `328` and the NHS number has authority `NHS`.
- **A40 NHS-ID update:** the LIMS authority is `MSH-3.1`.
- **A40 merge:** uses `MRG-1`, and the new identifier is the `PID-3` repetition with the same authority.

Both ER7 and HL7 v2 XML bodies are supported.

### Published message

- **Body:** a JSON object holding exactly the stored procedure parameters for the request type. The senders tell
  the two types apart from the body (only a merge has `OldIdentifier`), so no routing property is published.
- **Application properties:** the incoming properties are forwarded (`CorrelationId`, `WorkflowID`, `SourceSystem`, `MessageReceivedAt`, `MessageType`), plus:
  - `MessageControlId` (`MSH-10`), so the senders can log the request without logging the payload.
- **Session ID:** always `EGRESS_SESSION_ID`.

### Session IDs

Every subscription on the mapped topic is session-enabled. Each TRRR sender locks one session (`INGRESS_SESSION_ID`). Messages stamped with any other session ID sit in the subscription and are never delivered. They aren't dead-lettered either, so they look like "stuck" messages.

To avoid this, use one fixed value everywhere (`lims-trrr-mapped`):

| Setting | Value |
| --- | --- |
| Both mappers: `EGRESS_SESSION_ID` | `lims-trrr-mapped` |
| All 6 TRRR senders: `INGRESS_SESSION_ID` | `lims-trrr-mapped` |
| Both mappers: `INGRESS_SESSION_ID` | the LIMS SOAP server's `EGRESS_SESSION_ID` (`lims-soapserver`) |

`EGRESS_SESSION_ID` is required, so the mapper won't start without it.

### Failure handling

| Case | Result |
| --- | --- |
| Message can't be mapped (for example missing LIMS authority, missing NHS identifier, missing MRG) | Dead-lettered with `MappingFailed`. Nothing is published. |
| Publish to the mapped topic fails | Abandoned and retried. |
| Event logging fails after the publish | Logged, and the message is still completed. This avoids publishing twice. |

Only the MSH segment is logged. The NHS number and other PID data are never logged.

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `SERVICE_BUS_CONNECTION_STRING` / `SERVICE_BUS_NAMESPACE` | one of | Connection string locally; namespace with managed identity in Azure |
| `INGRESS_TOPIC_NAME` | yes | LIMS topic |
| `INGRESS_SUBSCRIPTION_NAME` | yes | NHS-ID or merge mapper subscription |
| `INGRESS_SESSION_ID` | no | Must match the LIMS publisher's session ID |
| `EGRESS_TOPIC_NAME` | yes | TRRR mapped topic |
| `EGRESS_SESSION_ID` | yes | Must match every TRRR sender's `INGRESS_SESSION_ID` |
| `TRRR_MAPPING_TYPE` | yes | `NHS_ID_UPDATE` or `MERGE` |
| `WORKFLOW_ID`, `MICROSERVICE_ID`, `HEALTH_BOARD`, `PEER_SERVICE` | no | Logging and metrics dimensions |
| `HEALTH_CHECK_HOST`, `HEALTH_CHECK_PORT` | no | TCP health check |
| `MAX_BATCH_SIZE` | no | Default `10` |

## Local development

```bash
uv sync
bash check.sh                                   # ruff, bandit, mypy, pytest
uv run python -m unittest discover tests        # unittest runner also works
```

In the local stack, the mappers run as `lims-trrr-nhsid-mapper` and `lims-trrr-merge-mapper` in the `lims-to-trrr` Compose profile
(both mappers + the ABMU sender). `lims-to-trrr-update` and `lims-to-trrr-merge` each run one mapper with all six board senders;
the split keeps each profile under the Service Bus emulator's 10-connection limit.
