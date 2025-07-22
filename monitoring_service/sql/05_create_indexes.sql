-- Performance Indexes for Integration Hub Tables
-- These indexes optimize query performance for the monitoring dashboard

-- Indexes for integrationhub.Event table (similar to fiorano.Event)
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

CREATE NONCLUSTERED INDEX [IX_IntegrationHubEvent_InsertedDateTime_EventDateTime_EventProcessName] 
ON [integrationhub].[Event] ([InsertedDateTime], [EventDateTime], [EventProcessName]) ON [PRIMARY]
GO

-- Indexes for integrationhub.Exception table (similar to Fiorano.Exception)
CREATE NONCLUSTERED INDEX [IX_IntegrationHubException_InsertedDateTime_EventDateTime_EventProcessName] 
ON [integrationhub].[Exception] ([InsertedDateTime], [EventDateTime], [EventProcessName]) ON [PRIMARY]
GO