-- PostgreSQL schema for the local Integration Hub message store.
--
-- Run automatically by the postgres container on first start: everything in
-- /docker-entrypoint-initdb.d is executed in filename order against POSTGRES_DB.
-- The database itself is created by the image from POSTGRES_DB, so there is no
-- CREATE DATABASE here (Postgres cannot create a database inside a transaction
-- block the way T-SQL's USE master / CREATE DATABASE did).
--
-- Identifiers use snake_case. Postgres folds unquoted identifiers to lower case,
-- so the previous PascalCase names would have required double-quoting in every
-- statement forever; snake_case avoids that entirely.

CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE IF NOT EXISTS monitoring.message
(
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Timestamps (stored as UTC)
    received_at          timestamptz(3) NOT NULL,
    stored_at            timestamptz(3) NOT NULL,
    -- Correlation / identifiers
    correlation_id       varchar(100)   NOT NULL,
    -- Source / processing context
    source_system        varchar(100)   NOT NULL,
    processing_component varchar(100)   NOT NULL,
    target_system        varchar(100)   NULL,
    -- Payloads
    raw_payload          text           NOT NULL,
    xml_payload          xml            NULL,
    -- Session routing (used by the message replay job)
    session_id           varchar(128)   NOT NULL
);

CREATE TABLE IF NOT EXISTS monitoring.message_replay_queue
(
    replay_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    replay_batch_id uuid           NOT NULL,
    message_id      bigint         NOT NULL,
    status          varchar(20)    NOT NULL DEFAULT 'Pending',
    created_at      timestamptz(3) NOT NULL DEFAULT now(),
    processed_at    timestamptz(3) NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_replay_queue_batch_message
    ON monitoring.message_replay_queue (replay_batch_id, message_id);

-- Partial index, equivalent to the SQL Server filtered index. Covers the
-- replay job's fetch query, which filters on batch + status and orders by replay_id.
CREATE INDEX IF NOT EXISTS ix_replay_queue_pending
    ON monitoring.message_replay_queue (replay_batch_id, replay_id)
    INCLUDE (message_id)
    WHERE status IN ('Pending', 'Failed');
