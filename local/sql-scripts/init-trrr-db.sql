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

-- Mock TRRR database for local testing of the db_sender TRRR instances (lims-to-trrr flow).
-- Identifiers are stored as text exactly as received (leading zeroes retained).

/****** Object:  Table [dbo].[TRRRIdentifierUpdate] ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TRRRIdentifierUpdate')
BEGIN
    CREATE TABLE [dbo].[TRRRIdentifierUpdate](
        [Id] [int] IDENTITY(1,1) NOT NULL,
        [LIMSIdentifier] [varchar](100) NOT NULL,
        [NewIdentifier] [varchar](100) NOT NULL,
        [NewIdentifierAssigningAuthority] [varchar](50) NOT NULL,
        [DateCreated] [datetime2](7) NOT NULL CONSTRAINT [DF_TRRRIdentifierUpdate_DateCreated] DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT [PK_TRRRIdentifierUpdate] PRIMARY KEY CLUSTERED ([Id] ASC)
    ) ON [PRIMARY];
END;
GO

/****** Object:  StoredProcedure [dbo].[TRRRIDUpdate] ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE OR ALTER PROCEDURE [dbo].[TRRRIDUpdate]
    @LIMSIdentifier VARCHAR(100),
    @NewIdentifier VARCHAR(100),
    @NewIdentifierAssigningAuthority VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO dbo.TRRRIdentifierUpdate ([LIMSIdentifier], [NewIdentifier], [NewIdentifierAssigningAuthority])
        VALUES (@LIMSIdentifier, @NewIdentifier, @NewIdentifierAssigningAuthority);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW;
    END CATCH;
END;
GO

/****** Object:  Table [dbo].[TRRRIdentifierMerge] ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TRRRIdentifierMerge')
BEGIN
    CREATE TABLE [dbo].[TRRRIdentifierMerge](
        [Id] [int] IDENTITY(1,1) NOT NULL,
        [OldIdentifier] [varchar](100) NOT NULL,
        [OldIdentifierAssigningAuthority] [varchar](50) NOT NULL,
        [NewIdentifier] [varchar](100) NOT NULL,
        [NewIdentifierAssigningAuthority] [varchar](50) NOT NULL,
        [DateCreated] [datetime2](7) NOT NULL CONSTRAINT [DF_TRRRIdentifierMerge_DateCreated] DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT [PK_TRRRIdentifierMerge] PRIMARY KEY CLUSTERED ([Id] ASC)
    ) ON [PRIMARY];
END;
GO

/****** Object:  StoredProcedure [dbo].[TRRRIDMerge] ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE OR ALTER PROCEDURE [dbo].[TRRRIDMerge]
    @OldIdentifier VARCHAR(100),
    @OldIdentifierAssigningAuthority VARCHAR(50),
    @NewIdentifier VARCHAR(100),
    @NewIdentifierAssigningAuthority VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO dbo.TRRRIdentifierMerge (
            [OldIdentifier],
            [OldIdentifierAssigningAuthority],
            [NewIdentifier],
            [NewIdentifierAssigningAuthority]
        )
        VALUES (
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
END;
GO
