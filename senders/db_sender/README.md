# Database Sender Service (`db_sender`)

## Overview

`db_sender` is a generic outbound microservice that consumes messages from Azure Service Bus subscriptions and executes configured stored procedures against Microsoft SQL Server databases.

It serves as the generic delivery engine for database integration flows in NHS Wales Integration Hub, starting with the **RISP to WRRS flow** (`dbo.prQueueMessage` in database `DRS`). Future database integrations can reuse this container by configuring environment variables without changing code.

### Procedure types (`DB_PROCEDURE_TYPE`)

| Type | Default stored procedure | Purpose |
|---|---|---|
| `queue_message` (default) | `dbo.prQueueMessage` | Passes the whole HL7 message (`@Message`, `@IsPriority`) - RISP to WRRS |
| `queue_id_update` | `dbo.prQueueIdUpdate` | WRRS identifier updates from A31 and A40 messages - LIMS to WRRS |
| `update_identifier` | `dbo.spUpdateIdentifier` | WCRS identifier update from A40 merges - CAV PMS to WCRS |

`update_identifier` accepts ADT^A40 only (HL7v2 XML or ER7). It passes three string parameters:
`OldIdentifier` (MRG-1.1), `OldIdentifierAssigningAuthority` (MRG-1.4.1, as-is) and `NewIdentifier` (the PID-3.1
whose PID-3.4.1 matches MRG-1.4.1). Missing values or a non-A40 trigger dead-letter the message
(`MissingOldIdentifier`, `MissingOldAssigningAuthority`, `MissingNewIdentifier`, `UnsupportedTriggerEvent`).

## Architecture

1. **Service Bus Ingress:** Subscribes to an Azure Service Bus topic subscription (supports session-enabled and non-session subscriptions).
2. **Strict Information Governance (IG) Logging:** Under Caldicott Principle 3, logs strictly record only the **MSH (Message Header)** portion of HL7 messages (both HL7 v2 XML and pipe-delimited ER7). Patient Identifiable Data (PID) and clinical payload segments (OBR, OBX, etc.) are never logged.
3. **Parameterised Stored Procedure Execution:** Invokes the configured stored procedure with `@Message` (payload) and `@IsPriority` (`bit`, defaulted to `0`).
4. **Error Handling & Resiliency:**
   - **Transient errors** (e.g. connection timeout, link failure, deadlock) abandon the Service Bus message for retry.
   - **Non-recoverable errors** (e.g. stored procedure missing, syntax error, permission denied) dead-letter the message to prevent blocking FIFO sessions.

## Environment Variables

| Variable | Description | Default / Example |
|---|---|---|
| `SERVICE_BUS_CONNECTION_STRING` | Service Bus connection string (local emulator) | None |
| `SERVICE_BUS_NAMESPACE` | Azure Service Bus namespace (cloud AAD) | None |
| `INGRESS_TOPIC_NAME` | Topic to consume from | `local-inthub-wrrs-outbound` |
| `INGRESS_SUBSCRIPTION_NAME` | Subscription to read from | `local-inthub-wrrs-outbound-sub` |
| `INGRESS_SESSION_ID` | Service Bus session ID | `risp-to-wrrs` |
| `DB_SERVER` | SQL Server hostname or container alias | `localhost` |
| `DB_PORT` | SQL Server port | `1433` |
| `DB_NAME` | Target database name | `DRS` |
| `DB_STORED_PROCEDURE` | Stored procedure to invoke | `dbo.prQueueMessage` (`dbo.prQueueIdUpdate` / `dbo.spUpdateIdentifier` for the other procedure types) |
| `DB_PROCEDURE_TYPE` | Handler strategy: `queue_message`, `queue_id_update` or `update_identifier` | `queue_message` |
| `DB_USERNAME` | SQL Auth username (local / dev) | None |
| `DB_PASSWORD` | SQL Auth password (local / dev) | None |
| `DB_ENCRYPT` | Enable TLS encryption | `Yes` |
| `DB_TRUST_SERVER_CERTIFICATE` | Trust server certificate (local / self-signed) | `No` (`Yes` for local dev) |
| `DB_CONNECTION_TIMEOUT` | Connection timeout in seconds | `30` |
| `DB_COMMAND_TIMEOUT` | Command execution timeout in seconds | `60` |
| `MANAGED_IDENTITY_CLIENT_ID` | Optional user-assigned MI client ID | None |
| `DEFAULT_IS_PRIORITY` | Default priority bit value | `0` |
| `WORKFLOW_ID` | Tracing workflow identifier | `risp-to-wrrs` |
| `MICROSERVICE_ID` | Microservice instance identifier | `wrrs_stmsg_dbsender` |
| `HEALTH_CHECK_HOST` | TCP health check bind host | `0.0.0.0` |
| `HEALTH_CHECK_PORT` | TCP health check port | `9000` |
| `LOG_LEVEL` | Python logging level | `INFO` |

## Local Development

Run tests and quality checks:
```bash
uv sync
bash check.sh
```
