USE master;
GO

-- fixes the error CREATE INDEX failed because the following SET options have incorrect settings: 'QUOTED_IDENTIFIER'. Verify that SET options are correct for use with indexes on computed columns
SET QUOTED_IDENTIFIER ON;
GO

-- Create database if not exists
IF NOT EXISTS (SELECT name
FROM sys.databases
WHERE name = 'IntegrationHub')
    BEGIN
    CREATE DATABASE IntegrationHub;
END;
GO

USE IntegrationHub;
GO

-- Create Schema
IF NOT EXISTS (SELECT *
FROM sys.schemas
WHERE name = 'monitoring')
    BEGIN
    EXEC('CREATE SCHEMA monitoring');
END;
GO

-- Create Table
IF NOT EXISTS (SELECT *
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'monitoring' AND TABLE_NAME = 'Message')
    BEGIN
    CREATE TABLE monitoring.Message
    (
        Id BIGINT IDENTITY(1,1) PRIMARY KEY,
        -- Timestamps
        ReceivedAt DATETIME2(3) NOT NULL,
        StoredAt DATETIME2(3) NOT NULL,
        -- Correlation / Identifiers
        CorrelationId NVARCHAR(100) NOT NULL,
        -- Source / Processing context
        SourceSystem NVARCHAR(100) NOT NULL,
        ProcessingComponent NVARCHAR(100) NOT NULL,
        TargetSystem NVARCHAR(100) NULL,
        -- Payloads
        RawPayload NVARCHAR(MAX) NOT NULL,
        XmlPayload XML NULL
    );
END;
GO

-- Create MessageReplayQueue Table
IF NOT EXISTS (SELECT *
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'monitoring' AND TABLE_NAME = 'MessageReplayQueue')
    BEGIN
    CREATE TABLE monitoring.MessageReplayQueue
    (
        ReplayId BIGINT IDENTITY(1,1) PRIMARY KEY,
        ReplayBatchId UNIQUEIDENTIFIER NOT NULL,
        MessageId BIGINT NOT NULL,
        Status VARCHAR(20) NOT NULL DEFAULT 'Pending',
        CreatedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        ProcessedAt DATETIME2(3) NULL
    );

    CREATE UNIQUE INDEX IX_ReplayQueue_Batch_Message
        ON monitoring.MessageReplayQueue (ReplayBatchId, MessageId);

    CREATE INDEX IX_ReplayQueue_Pending
        ON monitoring.MessageReplayQueue (ReplayBatchId, ReplayId)
        INCLUDE (MessageId)
        WHERE Status IN ('Pending', 'Failed');
END;
GO
