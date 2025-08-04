-- Integration Hub Exception Table (replaces fiorano.Exception)
CREATE TABLE [integrationhub].[Exception] (
    [Id] [bigint] NOT NULL IDENTITY(1, 1),
    [InsertedDateTime] [datetime2] (3) NOT NULL CONSTRAINT [DF_IntegrationHubException_InsertedDateTime] DEFAULT (getdate()),
    [EventDateTime] [datetime2] (0) NOT NULL,
    [UniqueEventId] [varchar] (800) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventProcessName] [varchar] (800) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventProcessVersionNumber] [varchar] (25) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventProcessComponentName] [varchar] (800) COLLATE Latin1_General_CI_AS NOT NULL,
    [PeerServer] [varchar] (256) COLLATE Latin1_General_CI_AS NOT NULL,
    [ErrorCode] [varchar] (max) COLLATE Latin1_General_CI_AS NULL,
    [ErrorMessage] [varchar] (max) COLLATE Latin1_General_CI_AS NULL,
    [ErrorDetail] [varchar] (max) COLLATE Latin1_General_CI_AS NULL,
    [ErrorData] [varchar] (max) COLLATE Latin1_General_CI_AS NULL,
    [FullException] [varchar] (max) COLLATE Latin1_General_CI_AS NOT NULL,
    [ApplicationContext] [varchar] (max) COLLATE Latin1_General_CI_AS NULL,
    [EventContext] [varchar] (max) COLLATE Latin1_General_CI_AS NOT NULL
) ON [PRIMARY]
GO

ALTER TABLE [integrationhub].[Exception] ADD CONSTRAINT [PK_IntegrationHubException] PRIMARY KEY CLUSTERED ([Id]) ON [PRIMARY]
GO