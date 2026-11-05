# TRRR Database Sender (`db_sender_trrr`)

## Overview

`db_sender_trrr` is a TRRR-specific database sender that mirrors the generic `db_sender` pattern while enforcing the LIMS/NHS identifier mapping for ADT_A05 messages.

It selects the ID values from `PID-3` by assigning authority:

- `328` -> `LIMSIdentifier`
- `NHS` -> `NewIdentifier`

The mapped values are then passed as a structured update request to the database layer only when both values are present. If either identifier is missing, the message is rejected and no database update request is created.

## Required environment variables

- `SERVICE_BUS_CONNECTION_STRING`
- `SERVICE_BUS_NAMESPACE`
- `INGRESS_TOPIC_NAME`
- `INGRESS_SUBSCRIPTION_NAME`
- `DB_SERVER` (default `TES06SRVSQLNOD1`)
- `DB_NAME` (default `Clinical_Results`)
- `DB_USERNAME` (default `TRRR`)
- `DB_PASSWORD` (default `trrr`)
- `DB_STORED_PROCEDURE` (default `dbo.prQueueMessage`)
- `WORKFLOW_ID`
- `MICROSERVICE_ID`

## Default database target

```text
jdbc:sqlserver://TES06SRVSQLNOD1;databaseName=Clinical_Results
user: TRRR
password: trrr
```

The service preserves identifier formatting exactly as received and does not coerce values to numeric types.
