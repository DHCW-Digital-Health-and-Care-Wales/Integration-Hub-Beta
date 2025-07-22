-- Event Processing Tracking Tables
-- These tables track which events have been processed and any processing errors

-- Table to track processed events
CREATE TABLE [queue].[ProcessedIntegrationHubEvent] (
    [ProcessedEventId] [bigint] NOT NULL IDENTITY(1, 1),
    [IntegrationHubEventId] [bigint] NOT NULL,
    [ProcessedDateTime] [datetime2] (3) NOT NULL,
    CONSTRAINT [PK_ProcessedIntegrationHubEvent] PRIMARY KEY CLUSTERED ([ProcessedEventId]),
    CONSTRAINT [FK_ProcessedIntegrationHubEvent_IntegrationHubEvent] FOREIGN KEY ([IntegrationHubEventId]) REFERENCES [queue].[IntegrationHubEvent] ([IntegrationHubEventId])
) ON [PRIMARY]
GO

-- Table to track processed exceptions
CREATE TABLE [queue].[ProcessedIntegrationHubException] (
    [ProcessedExceptionId] [bigint] NOT NULL IDENTITY(1, 1),
    [IntegrationHubExceptionId] [bigint] NOT NULL,
    [ProcessedDateTime] [datetime2] (3) NOT NULL,
    CONSTRAINT [PK_ProcessedIntegrationHubException] PRIMARY KEY CLUSTERED ([ProcessedExceptionId]),
    CONSTRAINT [FK_ProcessedIntegrationHubException_IntegrationHubException] FOREIGN KEY ([IntegrationHubExceptionId]) REFERENCES [queue].[IntegrationHubException] ([IntegrationHubExceptionId])
) ON [PRIMARY]
GO

-- Table to track event processing errors
CREATE TABLE [queue].[EventProcessingError] (
    [ErrorId] [bigint] NOT NULL IDENTITY(1, 1),
    [IntegrationHubEventId] [bigint] NOT NULL,
    [ErrorMessage] [varchar] (max) NOT NULL,
    [ErrorDateTime] [datetime2] (3) NOT NULL,
    CONSTRAINT [PK_EventProcessingError] PRIMARY KEY CLUSTERED ([ErrorId])
) ON [PRIMARY]
GO

-- Table to track exception processing errors
CREATE TABLE [queue].[ExceptionProcessingError] (
    [ErrorId] [bigint] NOT NULL IDENTITY(1, 1),
    [IntegrationHubExceptionId] [bigint] NOT NULL,
    [ErrorMessage] [varchar] (max) NOT NULL,
    [ErrorDateTime] [datetime2] (3) NOT NULL,
    CONSTRAINT [PK_ExceptionProcessingError] PRIMARY KEY CLUSTERED ([ErrorId])
) ON [PRIMARY]
GO