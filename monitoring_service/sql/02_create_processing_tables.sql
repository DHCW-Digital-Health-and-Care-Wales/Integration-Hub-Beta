-- Integration Hub Final Processing Tables
-- These tables store the processed/transformed audit events for dashboard consumption

-- Integration Hub Event Table (replaces fiorano.Event)
CREATE TABLE [integrationhub].[Event] (
    [Id] [bigint] NOT NULL IDENTITY(1, 1),
    [InsertedDateTime] [datetime2] (3) NOT NULL CONSTRAINT [DF_IntegrationHubEvent_InsertedDateTime] DEFAULT (getdate()),
    [EventDateTime] [datetime2] (0) NOT NULL,
    [UniqueEventId] [varchar] (800) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventProcessName] [varchar] (800) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventProcessVersionNumber] [varchar] (25) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventProcessComponentName] [varchar] (800) COLLATE Latin1_General_CI_AS NOT NULL,
    [PeerServer] [varchar] (256) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventMessage] [varchar] (max) COLLATE Latin1_General_CI_AS NOT NULL,
    [EventMessageXML] [xml] NULL,
    [ApplicationContext] [varchar] (max) COLLATE Latin1_General_CI_AS NULL,
    [EventContext] [varchar] (max) COLLATE Latin1_General_CI_AS NOT NULL
) ON [PRIMARY]
GO

ALTER TABLE [integrationhub].[Event] ADD CONSTRAINT [PK_IntegrationHubEvent] PRIMARY KEY CLUSTERED ([Id]) ON [PRIMARY]
GO

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