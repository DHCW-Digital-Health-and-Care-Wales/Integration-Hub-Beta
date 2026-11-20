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

-- Identifier updates and merges received by dbo.prQueueIdUpdate (LIMS to WRRS), so testers can see what was received.
IF OBJECT_ID('dbo.QueueIdUpdate', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.QueueIdUpdate (
        Id                              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_QueueIdUpdate PRIMARY KEY CLUSTERED,
        ProviderPatientIdentifier       VARCHAR(20)       NULL,
        ProviderAssigningAuthority      VARCHAR(10)       NULL,
        OldIdentifier                   VARCHAR(20)       NULL,
        OldIdentifierAssigningAuthority VARCHAR(10)       NULL,
        NewIdentifier                   VARCHAR(20)       NOT NULL,
        NewIdentifierAssigningAuthority VARCHAR(10)       NOT NULL,
        DateCreated                     DATETIME2(7)      NOT NULL
            CONSTRAINT DF_QueueIdUpdate_DateCreated DEFAULT (SYSUTCDATETIME())
    );
END;
GO

-- Mock of the WRRS identifier update procedure (same six parameters as the real one).
-- Per-call scenarios, selected by the NewIdentifier value:
--   MOCK_ERROR   -> THROW a SQL error, as the real CATCH block does          (sender dead-letters)
--   MOCK_REJECT  -> RETURN 55555, nothing stored                              (failure return code)
--   MOCK_TIMEOUT -> delay longer than the sender's command timeout            (sender retries)
-- Any other value falls back to the global dbo.MockControl switch; by default the call is stored.
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
        THROW 50001, 'Mock SQL error requested by MOCK_ERROR', 1;
    END;

    IF @scenario = 'REJECT'
        RETURN 55555;

    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO dbo.QueueIdUpdate (
            ProviderPatientIdentifier, ProviderAssigningAuthority, OldIdentifier,
            OldIdentifierAssigningAuthority, NewIdentifier, NewIdentifierAssigningAuthority
        )
        VALUES (
            @ProviderPatientIdentifier, @ProviderAssigningAuthority, @OldIdentifier,
            @OldIdentifierAssigningAuthority, @NewIdentifier, @NewIdentifierAssigningAuthority
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

-- Receives the LIMS -> NHS identifier associations (NHS_ID_UPDATE requests) written by db_sender_trrr.
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

-- Superseded by dbo.spProcessResult; dropped so an existing mock database does not keep stale procedures.
DROP PROCEDURE IF EXISTS dbo.TRRRIDUpdate;
DROP PROCEDURE IF EXISTS dbo.TRRRIDMerge;
GO

-- TRRR processes both request types through one procedure, called positionally by db_sender_trrr's
-- db_client.execute_identifier_update:
--   NHS_ID_UPDATE (3 args): LIMSIdentifier, NewIdentifier, NewIdentifierAssigningAuthority
--   MERGE         (4 args): OldIdentifier, OldIdentifierAssigningAuthority, NewIdentifier,
--                           NewIdentifierAssigningAuthority
-- The mock distinguishes them by whether the 4th argument was supplied and writes to the matching table.
-- Arguments may be blank when the source message did not map them; all are text and are stored exactly as
-- received (leading zeroes retained).
CREATE OR ALTER PROCEDURE dbo.spProcessResult
    @Param1 VARCHAR(100),
    @Param2 VARCHAR(100),
    @Param3 VARCHAR(100),
    @Param4 VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        IF @Param4 IS NULL
            INSERT INTO dbo.TRRRIdentifierUpdate (LIMSIdentifier, NewIdentifier, NewIdentifierAssigningAuthority)
            VALUES (@Param1, @Param2, @Param3);
        ELSE
            INSERT INTO dbo.TRRRIdentifierMerge
                (OldIdentifier, OldIdentifierAssigningAuthority, NewIdentifier, NewIdentifierAssigningAuthority)
            VALUES (@Param1, @Param2, @Param3, @Param4);
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END
GO

-- =============================================================================================
-- Mock WCRS "NDR" database for local testing of the CAV PMS -> WCRS flow (db_sender with
-- DB_PROCEDURE_TYPE=update_identifier). Independent of DRS and Clinical_Results above.
-- =============================================================================================
USE master;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'NDR')
BEGIN
    CREATE DATABASE NDR;
END;
GO

USE [NDR];
GO

-- Receives the identifier updates written via dbo.spUpdateIdentifier, so testers can see what was received.
IF OBJECT_ID('dbo.IdentifierUpdate', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.IdentifierUpdate (
        Id                              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_IdentifierUpdate PRIMARY KEY CLUSTERED,
        OldIdentifier                   VARCHAR(100)      NOT NULL,
        OldIdentifierAssigningAuthority VARCHAR(50)       NOT NULL,
        NewIdentifier                   VARCHAR(100)      NOT NULL,
        ReceivedUtc                     DATETIME2(7)      NOT NULL CONSTRAINT DF_IdentifierUpdate_ReceivedUtc DEFAULT (SYSUTCDATETIME())
    );
END;
GO

-- The real procedure's full definition is not available, so this only stores its three inputs.
-- Parameter order matches db_sender's execute_update_identifier. Arguments are text and are stored exactly
-- as received (leading zeroes retained).
CREATE OR ALTER PROCEDURE dbo.spUpdateIdentifier
    @OldIdentifier                   VARCHAR(100),
    @OldIdentifierAssigningAuthority VARCHAR(50),
    @NewIdentifier                   VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        INSERT INTO dbo.IdentifierUpdate (OldIdentifier, OldIdentifierAssigningAuthority, NewIdentifier)
        VALUES (@OldIdentifier, @OldIdentifierAssigningAuthority, @NewIdentifier);
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END
GO
