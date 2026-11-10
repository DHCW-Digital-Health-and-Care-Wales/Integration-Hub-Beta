-- Mock WRRS "DRS" database for local testing of senders/db_sender.
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

-- Single-row switch that forces a scenario for every call (a per-message token overrides it).
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

-- =============================================================================================
-- Mock TRRR "Clinical_Results" database for local testing of senders/db_sender_trrr
-- (lims-to-trrr flow). Independent of DRS above.
-- =============================================================================================
USE master;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'Clinical_Results')
BEGIN
    CREATE DATABASE Clinical_Results;
END;
GO

USE [Clinical_Results];
GO

-- Receives the LIMS -> NHS identifier associations written by db_sender_trrr.
IF OBJECT_ID('dbo.TRRRIdentifierUpdate', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TRRRIdentifierUpdate (
        Id                             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TRRRIdentifierUpdate PRIMARY KEY CLUSTERED,
        LIMSIdentifier                 VARCHAR(100)      NOT NULL,
        NewIdentifier                  VARCHAR(100)      NOT NULL,
        NewIdentifierAssigningAuthority VARCHAR(50)      NOT NULL,
        ReceivedUtc                    DATETIME2(7)      NOT NULL CONSTRAINT DF_TRRRIdentifierUpdate_ReceivedUtc DEFAULT (SYSUTCDATETIME())
    );
END;
GO

-- Signature must match db_sender_trrr's db_client.execute_identifier_update:
-- (LIMSIdentifier, NewIdentifier, NewIdentifierAssigningAuthority). All arguments are text and are
-- stored exactly as received (leading zeroes retained).
CREATE OR ALTER PROCEDURE dbo.TRRRIDUpdate
    @LIMSIdentifier                  VARCHAR(100),
    @NewIdentifier                   VARCHAR(100),
    @NewIdentifierAssigningAuthority VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        INSERT INTO dbo.TRRRIdentifierUpdate (LIMSIdentifier, NewIdentifier, NewIdentifierAssigningAuthority)
        VALUES (@LIMSIdentifier, @NewIdentifier, @NewIdentifierAssigningAuthority);
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END
GO

-- Receives the patient merge (superseded -> replacement identifier) requests written by db_sender_trrr
-- for ADT^A40 messages.
IF OBJECT_ID('dbo.TRRRIdentifierMerge', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TRRRIdentifierMerge (
        Id                              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_TRRRIdentifierMerge PRIMARY KEY CLUSTERED,
        OldIdentifier                   VARCHAR(100)      NOT NULL,
        OldIdentifierAssigningAuthority VARCHAR(50)       NOT NULL,
        NewIdentifier                   VARCHAR(100)      NOT NULL,
        NewIdentifierAssigningAuthority VARCHAR(50)       NOT NULL,
        ReceivedUtc                     DATETIME2(7)      NOT NULL CONSTRAINT DF_TRRRIdentifierMerge_ReceivedUtc DEFAULT (SYSUTCDATETIME())
    );
END;
GO

-- Signature must match db_sender_trrr's db_client.execute_identifier_update for merge requests:
-- (OldIdentifier, OldIdentifierAssigningAuthority, NewIdentifier, NewIdentifierAssigningAuthority).
-- All arguments are text and are stored exactly as received (leading zeroes retained).
CREATE OR ALTER PROCEDURE dbo.TRRRIDMerge
    @OldIdentifier                   VARCHAR(100),
    @OldIdentifierAssigningAuthority VARCHAR(50),
    @NewIdentifier                   VARCHAR(100),
    @NewIdentifierAssigningAuthority VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        INSERT INTO dbo.TRRRIdentifierMerge
            (OldIdentifier, OldIdentifierAssigningAuthority, NewIdentifier, NewIdentifierAssigningAuthority)
        VALUES
            (@OldIdentifier, @OldIdentifierAssigningAuthority, @NewIdentifier, @NewIdentifierAssigningAuthority);
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END
GO