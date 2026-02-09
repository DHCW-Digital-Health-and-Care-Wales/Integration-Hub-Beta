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
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'monitoring' AND TABLE_NAME = 'Messages')
    BEGIN
        CREATE TABLE monitoring.Messages (
            MessageId BIGINT IDENTITY(1,1) PRIMARY KEY,
            -- Timestamps
            MessageReceivedAt DATETIME2(3) NOT NULL,
            MessageStoredAt DATETIME2(3) NOT NULL,
            -- Correlation / Identifiers
            EventId NVARCHAR(100) NOT NULL,
            WorkflowId NVARCHAR(100) NOT NULL,
            -- Source / Processing context
            SourceSystem NVARCHAR(100) NOT NULL,
            ProcessingComponent NVARCHAR(100) NOT NULL,
            TargetSystem NVARCHAR(100) NULL,
            -- Payloads
            RawMessagePayload NVARCHAR(MAX) NOT NULL,
            MessageXml XML NULL
        );
    END;
GO
