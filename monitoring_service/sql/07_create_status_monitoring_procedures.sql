-- Status Monitoring Stored Procedures
-- These procedures handle component, workflow, and infrastructure status updates

-- Stored Procedure to Update Enterprise Server Status
CREATE PROCEDURE [integrationhub].[prInsertEnterpriseServerStatus]
    @ServerName VARCHAR(256),
    @Status VARCHAR(50),
    @Version VARCHAR(50) = NULL,
    @Environment VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    INSERT INTO [integrationhub].[EnterpriseServerStatus]
    ([ServerName], [Status], [LastHeartbeat], [Version], [Environment])
    VALUES (@ServerName, @Status, GETDATE(), @Version, @Environment);
END
GO

-- Stored Procedure to Update Event Process Status
CREATE PROCEDURE [integrationhub].[prInsertEventProcessStatus]
    @WorkflowId VARCHAR(256),
    @WorkflowName VARCHAR(256),
    @Status VARCHAR(50),
    @MessagesProcessed BIGINT = 0,
    @ErrorCount BIGINT = 0
AS
BEGIN
    SET NOCOUNT ON;
    
    INSERT INTO [integrationhub].[EventProcessStatus]
    ([WorkflowId], [WorkflowName], [Status], [LastActivity], [MessagesProcessed], [ErrorCount])
    VALUES (@WorkflowId, @WorkflowName, @Status, GETDATE(), @MessagesProcessed, @ErrorCount);
END
GO

-- Stored Procedure to Update Component Status
CREATE PROCEDURE [integrationhub].[prInsertEventComponentStatus]
    @ComponentId VARCHAR(256),
    @ComponentName VARCHAR(256),
    @WorkflowId VARCHAR(256),
    @Status VARCHAR(50),
    @MessagesProcessed BIGINT = 0,
    @ErrorCount BIGINT = 0
AS
BEGIN
    SET NOCOUNT ON;
    
    INSERT INTO [integrationhub].[EventComponentStatus]
    ([ComponentId], [ComponentName], [WorkflowId], [Status], [LastActivity], [MessagesProcessed], [ErrorCount])
    VALUES (@ComponentId, @ComponentName, @WorkflowId, @Status, GETDATE(), @MessagesProcessed, @ErrorCount);
END
GO

-- Stored Procedure to Update Service Bus Queue Status
CREATE PROCEDURE [integrationhub].[prInsertServiceBusQueueStatus]
    @QueueName VARCHAR(256),
    @MessageCount BIGINT,
    @DeadLetterMessageCount BIGINT,
    @Status VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;
    
    INSERT INTO [integrationhub].[ServiceBusQueueStatus]
    ([QueueName], [MessageCount], [DeadLetterMessageCount], [Status], [LastUpdated])
    VALUES (@QueueName, @MessageCount, @DeadLetterMessageCount, @Status, GETDATE());
END
GO