USE master;
GO

-- Create database if not exists
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'IntegrationHub')
    BEGIN
        CREATE DATABASE IntegrationHub;
    END;
GO

USE IntegrationHub;
GO

-- Create Schema
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'monitoring')
    BEGIN
        EXEC('CREATE SCHEMA monitoring');
    END;
GO

-- Create Table
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'monitoring' AND TABLE_NAME = 'Message')
    BEGIN
        CREATE TABLE monitoring.Message (
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
