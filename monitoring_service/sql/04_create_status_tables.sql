-- Status Monitoring Tables
-- These tables store component, workflow, and infrastructure status information

-- Integration Hub Enterprise Server Status
CREATE TABLE [integrationhub].[EnterpriseServerStatus] (
    [Id] [bigint] NOT NULL IDENTITY(1, 1),
    [ServerName] [varchar] (256) NOT NULL,
    [Status] [varchar] (50) NOT NULL,
    [LastHeartbeat] [datetime2] (3) NOT NULL,
    [InsertedDateTime] [datetime2] (3) NOT NULL DEFAULT (getdate()),
    [Version] [varchar] (50) NULL,
    [Environment] [varchar] (50) NULL,
    CONSTRAINT [PK_EnterpriseServerStatus] PRIMARY KEY CLUSTERED ([Id])
) ON [PRIMARY]
GO

-- Integration Hub Event Process Status (Workflows)
CREATE TABLE [integrationhub].[EventProcessStatus] (
    [Id] [bigint] NOT NULL IDENTITY(1, 1),
    [WorkflowId] [varchar] (256) NOT NULL,
    [WorkflowName] [varchar] (256) NOT NULL,
    [Status] [varchar] (50) NOT NULL,
    [LastActivity] [datetime2] (3) NOT NULL,
    [InsertedDateTime] [datetime2] (3) NOT NULL DEFAULT (getdate()),
    [MessagesProcessed] [bigint] NULL DEFAULT (0),
    [ErrorCount] [bigint] NULL DEFAULT (0),
    CONSTRAINT [PK_EventProcessStatus] PRIMARY KEY CLUSTERED ([Id])
) ON [PRIMARY]
GO

-- Integration Hub Component Status
CREATE TABLE [integrationhub].[EventComponentStatus] (
    [Id] [bigint] NOT NULL IDENTITY(1, 1),
    [ComponentId] [varchar] (256) NOT NULL,
    [ComponentName] [varchar] (256) NOT NULL,
    [WorkflowId] [varchar] (256) NOT NULL,
    [Status] [varchar] (50) NOT NULL,
    [LastActivity] [datetime2] (3) NOT NULL,
    [InsertedDateTime] [datetime2] (3) NOT NULL DEFAULT (getdate()),
    [MessagesProcessed] [bigint] NULL DEFAULT (0),
    [ErrorCount] [bigint] NULL DEFAULT (0),
    CONSTRAINT [PK_EventComponentStatus] PRIMARY KEY CLUSTERED ([Id])
) ON [PRIMARY]
GO

-- Integration Hub Service Bus Queue Status
CREATE TABLE [integrationhub].[ServiceBusQueueStatus] (
    [Id] [bigint] NOT NULL IDENTITY(1, 1),
    [QueueName] [varchar] (256) NOT NULL,
    [MessageCount] [bigint] NOT NULL,
    [DeadLetterMessageCount] [bigint] NOT NULL,
    [Status] [varchar] (50) NOT NULL,
    [LastUpdated] [datetime2] (3) NOT NULL,
    [InsertedDateTime] [datetime2] (3) NOT NULL DEFAULT (getdate()),
    CONSTRAINT [PK_ServiceBusQueueStatus] PRIMARY KEY CLUSTERED ([Id])
) ON [PRIMARY]
GO