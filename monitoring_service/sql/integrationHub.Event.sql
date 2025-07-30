-- Integration Hub Event Table
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

-- Indexes for integrationhub.Event table
CREATE NONCLUSTERED INDEX [IX_IntegrationHubEvent_EventDateTime_With_EventProcessName_EventProcessComponentName_UniqueEventId] 
ON [integrationhub].[Event] ([EventDateTime]) 
INCLUDE ([EventProcessName], [EventProcessComponentName], [UniqueEventId]) ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_IntegrationHubEvent_EventProcessComponentName_EventDateTime] 
ON [integrationhub].[Event] ([EventProcessComponentName], [EventDateTime]) 
INCLUDE ([UniqueEventId], [EventProcessName]) ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_IntegrationHubEvent_EventProcessName_EventDateTime_Include_UniqueEventId] 
ON [integrationhub].[Event] ([EventProcessName], [EventDateTime]) 
INCLUDE ([UniqueEventId]) ON [PRIMARY]
GO
