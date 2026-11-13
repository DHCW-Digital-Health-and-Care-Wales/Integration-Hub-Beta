-- Mock WRRS "DRS" database for local/dev testing of senders/db_sender.
-- Serves both WRRS flows: dbo.prQueueMessage (RISP -> WRRS) and dbo.prQueueIdUpdate (LIMS -> WRRS).
-- Idempotent: safe to run on every container start.
SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'DRS')
BEGIN
    CREATE DATABASE DRS;
END;
GO

USE [DRS];
GO

-- Every successful call to the mock procedure is recorded here so testers can see what was received.
IF OBJECT_ID('dbo.QueueMessage', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.QueueMessage (
        Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_QueueMessage PRIMARY KEY CLUSTERED,
        ReceivedAtUtc DATETIME2(3)      NOT NULL CONSTRAINT DF_QueueMessage_ReceivedAtUtc DEFAULT (SYSUTCDATETIME()),
        Message       VARCHAR(MAX)      NOT NULL,
        MessageXML    XML               NULL,
        IsPriority    BIT               NOT NULL CONSTRAINT DF_QueueMessage_IsPriority DEFAULT (0)
    );
END;
GO

-- Every successful call to dbo.prQueueIdUpdate is recorded here (LIMS -> WRRS identifier updates).
IF OBJECT_ID('dbo.QueueIdUpdate', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.QueueIdUpdate (
        Id                               INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_QueueIdUpdate PRIMARY KEY CLUSTERED,
        ProviderPatientIdentifier        VARCHAR(20)       NULL,
        ProviderAssigningAuthority       VARCHAR(10)       NULL,
        OldIdentifier                    VARCHAR(20)       NULL,
        OldIdentifierAssigningAuthority  VARCHAR(10)       NULL,
        NewIdentifier                    VARCHAR(20)       NOT NULL,
        NewIdentifierAssigningAuthority  VARCHAR(10)       NOT NULL,
        DateCreated                      DATETIME2(7)      NOT NULL CONSTRAINT DF_QueueIdUpdate_DateCreated DEFAULT (SYSUTCDATETIME())
    );
END;
GO

-- Single-row switch that forces a scenario for every call to either procedure
-- (a per-message token / sentinel identifier overrides it).
-- Valid values: NONE, REJECT, ERROR, TIMEOUT.
IF OBJECT_ID('dbo.MockControl', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.MockControl (
        Id       INT         NOT NULL CONSTRAINT PK_MockControl PRIMARY KEY CONSTRAINT CK_MockControl_Id CHECK (Id = 1),
        Scenario VARCHAR(20) NOT NULL CONSTRAINT DF_MockControl_Scenario DEFAULT ('NONE')
            CONSTRAINT CK_MockControl_Scenario CHECK (Scenario IN ('NONE', 'REJECT', 'ERROR', 'TIMEOUT'))
    );
    INSERT INTO dbo.MockControl (Id, Scenario) VALUES (1, 'NONE');
END;
GO

-- Mirrors the contract of the real procedure:
--   success -> returns nothing (implicit return code 0, no result set)
--   failure -> RETURN 55555 (a return code; no SQL error is raised)
-- ERROR and TIMEOUT scenarios exist only to exercise the sender's SQL error / timeout handling.
CREATE OR ALTER PROCEDURE dbo.prQueueMessage
    @Message    VARCHAR(MAX),
    @IsPriority BIT = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @scenario VARCHAR(20);

    -- A token in the (synthetic) test message wins over the global switch.
    IF @Message LIKE '%MOCK_SCENARIO=REJECT%'       SET @scenario = 'REJECT';
    ELSE IF @Message LIKE '%MOCK_SCENARIO=ERROR%'   SET @scenario = 'ERROR';
    ELSE IF @Message LIKE '%MOCK_SCENARIO=TIMEOUT%' SET @scenario = 'TIMEOUT';
    ELSE SELECT @scenario = Scenario FROM dbo.MockControl WHERE Id = 1;

    IF @scenario = 'TIMEOUT'
    BEGIN
        -- Longer than the sender's default DB_COMMAND_TIMEOUT (60s) so it surfaces as a query timeout.
        WAITFOR DELAY '00:01:30';
    END;

    IF @scenario = 'ERROR'
    BEGIN
        THROW 50001, 'Mock SQL error requested by MOCK_SCENARIO=ERROR', 1;
    END;

    IF @scenario = 'REJECT'
        RETURN 55555;

    BEGIN TRY
        DECLARE @doc XML = CAST(REPLACE(@Message, ' encoding="UTF-8"', '') AS XML);

        INSERT INTO dbo.QueueMessage (Message, MessageXML, IsPriority)
        VALUES (@Message, @doc, @IsPriority);
    END TRY
    BEGIN CATCH
        -- Like the real procedure, a message it cannot store is reported as a failure return code.
        RETURN 55555;
    END CATCH;
END
GO

-- LIMS -> WRRS identifier update. Same contract as the real procedure:
--   success -> returns nothing (implicit return code 0, no result set)
--   failure -> a SQL error is raised (the sender dead-letters it as a fatal error)
-- Failure scenarios are triggered by a sentinel @NewIdentifier (testers control the identifier in the
-- synthetic message) or globally via dbo.MockControl. The sentinels fit the VARCHAR(20) column:
--   MOCK_REJECT  -> RETURN 55555 (failure return code, no SQL error)
--   MOCK_ERROR   -> THROW 50001 (SQL error)
--   MOCK_TIMEOUT -> WAITFOR longer than the sender's command timeout
CREATE OR ALTER PROCEDURE dbo.prQueueIdUpdate
    @ProviderPatientIdentifier       VARCHAR(20) = NULL,
    @ProviderAssigningAuthority      VARCHAR(10) = NULL,
    @OldIdentifier                   VARCHAR(20) = NULL,
    @OldIdentifierAssigningAuthority VARCHAR(10) = NULL,
    @NewIdentifier                   VARCHAR(20),
    @NewIdentifierAssigningAuthority VARCHAR(10)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @scenario VARCHAR(20);

    IF @NewIdentifier = 'MOCK_REJECT'       SET @scenario = 'REJECT';
    ELSE IF @NewIdentifier = 'MOCK_ERROR'   SET @scenario = 'ERROR';
    ELSE IF @NewIdentifier = 'MOCK_TIMEOUT' SET @scenario = 'TIMEOUT';
    ELSE SELECT @scenario = Scenario FROM dbo.MockControl WHERE Id = 1;

    IF @scenario = 'TIMEOUT'
    BEGIN
        -- Longer than the sender's default DB_COMMAND_TIMEOUT (60s) so it surfaces as a query timeout.
        WAITFOR DELAY '00:01:30';
    END;

    IF @scenario = 'ERROR'
    BEGIN
        THROW 50001, 'Mock SQL error requested by MOCK_ERROR / MockControl ERROR', 1;
    END;

    IF @scenario = 'REJECT'
        RETURN 55555;

    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO dbo.QueueIdUpdate (
            ProviderPatientIdentifier,
            ProviderAssigningAuthority,
            OldIdentifier,
            OldIdentifierAssigningAuthority,
            NewIdentifier,
            NewIdentifierAssigningAuthority
        )
        VALUES (
            @ProviderPatientIdentifier,
            @ProviderAssigningAuthority,
            @OldIdentifier,
            @OldIdentifierAssigningAuthority,
            @NewIdentifier,
            @NewIdentifierAssigningAuthority
        );

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW;
    END CATCH;
END
GO
