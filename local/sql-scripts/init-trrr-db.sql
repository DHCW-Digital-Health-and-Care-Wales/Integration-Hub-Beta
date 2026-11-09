USE master;
GO

SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'Clinical_Results')
BEGIN
    CREATE DATABASE Clinical_Results;
END;
GO

USE [Clinical_Results];
GO

SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

/****** Table to receive LIMS -> NHS identifier associations written by db_sender_trrr ******/
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TRRRIdentifierUpdate')
BEGIN
    CREATE TABLE [dbo].[TRRRIdentifierUpdate](
        [Id] [int] IDENTITY(1,1) NOT NULL,
        [LIMSIdentifier] [varchar](100) NOT NULL,
        [NewIdentifier] [varchar](100) NOT NULL,
        [NewIdentifierAssigningAuthority] [varchar](50) NOT NULL,
        [ReceivedUtc] [datetime2](7) NOT NULL CONSTRAINT [DF_TRRRIdentifierUpdate_ReceivedUtc] DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT [PK_TRRRIdentifierUpdate] PRIMARY KEY CLUSTERED
        (
            [Id] ASC
        )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
    ) ON [PRIMARY];
END;
GO

SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

-- =============================================
-- Stored procedure invoked by db_sender_trrr.
-- All three arguments are passed as text and preserved exactly (leading zeroes retained).
-- Signature must match db_client.execute_identifier_update: (LIMSIdentifier, NewIdentifier,
-- NewIdentifierAssigningAuthority).
-- =============================================
CREATE OR ALTER PROCEDURE [dbo].[TRRRIDUpdate]
    @LIMSIdentifier VARCHAR(100),
    @NewIdentifier VARCHAR(100),
    @NewIdentifierAssigningAuthority VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        INSERT INTO dbo.TRRRIdentifierUpdate ([LIMSIdentifier], [NewIdentifier], [NewIdentifierAssigningAuthority])
        VALUES (@LIMSIdentifier, @NewIdentifier, @NewIdentifierAssigningAuthority);
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END
GO
