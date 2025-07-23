-- Integration Hub Exception Queue Table
CREATE TABLE [queue].[IntegrationHubException] (
    [IntegrationHubExceptionId] [bigint] NOT NULL IDENTITY(1, 1),
    [EventCategory] [varchar] (256) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventType] [varchar] (256) COLLATE Latin1_General_CI_AS NOT NULL,
    [Event] [varchar] (max) COLLATE Latin1_General_CI_AS NOT NULL,
    [InsertedDateTime] [datetime2] (0) NOT NULL CONSTRAINT [DF_IntegrationHubException_InsertedDateTime] DEFAULT (getdate()),
    [EventXML] [xml] NULL
) ON [PRIMARY]
GO

ALTER TABLE [queue].[IntegrationHubException] ADD CONSTRAINT [PK_IntegrationHubException] PRIMARY KEY CLUSTERED ([IntegrationHubExceptionId]) ON [PRIMARY]
GO

ALTER TABLE [queue].[IntegrationHubException] ADD CONSTRAINT [FK_IntegrationHubException_EventType] FOREIGN KEY ([EventType]) REFERENCES [config].[EventType] ([EventType])
GO