-- Event Processing Stored Procedures
-- These procedures transform raw audit events into structured monitoring data

-- Stored Procedure to Process Integration Hub Events
CREATE PROCEDURE [queue].[prProcessIntegrationHubEvent]
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @EventId BIGINT;
    DECLARE @EventCategory VARCHAR(256);
    DECLARE @EventType VARCHAR(256);
    DECLARE @Event VARCHAR(MAX);
    DECLARE @EventXML XML;
    
    -- Cursor to process unprocessed events
    DECLARE event_cursor CURSOR FOR
    SELECT [IntegrationHubEventId], [EventCategory], [EventType], [Event], [EventXML]
    FROM [queue].[IntegrationHubEvent]
    WHERE [IntegrationHubEventId] NOT IN (SELECT [IntegrationHubEventId] FROM [queue].[ProcessedIntegrationHubEvent]);
    
    OPEN event_cursor;
    FETCH NEXT FROM event_cursor INTO @EventId, @EventCategory, @EventType, @Event, @EventXML;
    
    WHILE @@FETCH_STATUS = 0
    BEGIN
        BEGIN TRY
            -- Extract event data from JSON/XML and insert into integrationhub.Event table
            DECLARE @EventDateTime DATETIME2(0);
            DECLARE @UniqueEventId VARCHAR(800);
            DECLARE @EventProcessName VARCHAR(800);
            DECLARE @EventProcessVersionNumber VARCHAR(25);
            DECLARE @EventProcessComponentName VARCHAR(800);
            DECLARE @PeerServer VARCHAR(256);
            DECLARE @EventMessage VARCHAR(MAX);
            DECLARE @EventMessageXML XML;
            DECLARE @ApplicationContext VARCHAR(MAX);
            DECLARE @EventContext VARCHAR(MAX);
            
            -- Parse JSON event data (assuming JSON format from audit events)
            SELECT 
                @EventDateTime = ISNULL(TRY_CAST(JSON_VALUE(@Event, '$.timestamp') AS DATETIME2(0)), GETDATE()),
                @UniqueEventId = ISNULL(JSON_VALUE(@Event, '$.workflow_id'), '') + '_' + ISNULL(JSON_VALUE(@Event, '$.microservice_id'), ''),
                @EventProcessName = ISNULL(JSON_VALUE(@Event, '$.workflow_id'), 'Unknown'),
                @EventProcessVersionNumber = '1.0',
                @EventProcessComponentName = ISNULL(JSON_VALUE(@Event, '$.microservice_id'), 'Unknown'),
                @PeerServer = @@SERVERNAME,
                @EventMessage = ISNULL(JSON_VALUE(@Event, '$.message_content'), @Event),
                @EventMessageXML = NULL,
                @ApplicationContext = NULL,
                @EventContext = @Event;
            
            -- Insert into integrationhub.Event table
            INSERT INTO [integrationhub].[Event] (
                [EventDateTime],
                [UniqueEventId],
                [EventProcessName],
                [EventProcessVersionNumber],
                [EventProcessComponentName],
                [PeerServer],
                [EventMessage],
                [EventMessageXML],
                [ApplicationContext],
                [EventContext]
            )
            VALUES (
                @EventDateTime,
                @UniqueEventId,
                @EventProcessName,
                @EventProcessVersionNumber,
                @EventProcessComponentName,
                @PeerServer,
                @EventMessage,
                @EventMessageXML,
                @ApplicationContext,
                @EventContext
            );
            
            -- Mark event as processed
            INSERT INTO [queue].[ProcessedIntegrationHubEvent] ([IntegrationHubEventId], [ProcessedDateTime])
            VALUES (@EventId, GETDATE());
            
        END TRY
        BEGIN CATCH
            -- Log processing error
            INSERT INTO [queue].[EventProcessingError] ([IntegrationHubEventId], [ErrorMessage], [ErrorDateTime])
            VALUES (@EventId, ERROR_MESSAGE(), GETDATE());
        END CATCH
        
        FETCH NEXT FROM event_cursor INTO @EventId, @EventCategory, @EventType, @Event, @EventXML;
    END
    
    CLOSE event_cursor;
    DEALLOCATE event_cursor;
END
GO

-- Stored Procedure to Process Integration Hub Exceptions
CREATE PROCEDURE [queue].[prProcessIntegrationHubException]
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @ExceptionId BIGINT;
    DECLARE @EventCategory VARCHAR(256);
    DECLARE @EventType VARCHAR(256);
    DECLARE @Event VARCHAR(MAX);
    DECLARE @EventXML XML;
    
    -- Cursor to process unprocessed exceptions
    DECLARE exception_cursor CURSOR FOR
    SELECT [IntegrationHubExceptionId], [EventCategory], [EventType], [Event], [EventXML]
    FROM [queue].[IntegrationHubException]
    WHERE [IntegrationHubExceptionId] NOT IN (SELECT [IntegrationHubExceptionId] FROM [queue].[ProcessedIntegrationHubException]);
    
    OPEN exception_cursor;
    FETCH NEXT FROM exception_cursor INTO @ExceptionId, @EventCategory, @EventType, @Event, @EventXML;
    
    WHILE @@FETCH_STATUS = 0
    BEGIN
        BEGIN TRY
            -- Extract exception data from JSON and insert into integrationhub.Exception table
            DECLARE @EventDateTime DATETIME2(0);
            DECLARE @UniqueEventId VARCHAR(800);
            DECLARE @EventProcessName VARCHAR(800);
            DECLARE @EventProcessVersionNumber VARCHAR(25);
            DECLARE @EventProcessComponentName VARCHAR(800);
            DECLARE @PeerServer VARCHAR(256);
            DECLARE @ErrorCode VARCHAR(MAX);
            DECLARE @ErrorMessage VARCHAR(MAX);
            DECLARE @ErrorDetail VARCHAR(MAX);
            DECLARE @ErrorData VARCHAR(MAX);
            DECLARE @FullException VARCHAR(MAX);
            DECLARE @ApplicationContext VARCHAR(MAX);
            DECLARE @EventContext VARCHAR(MAX);
            
            -- Parse JSON exception data
            SELECT 
                @EventDateTime = ISNULL(TRY_CAST(JSON_VALUE(@Event, '$.timestamp') AS DATETIME2(0)), GETDATE()),
                @UniqueEventId = ISNULL(JSON_VALUE(@Event, '$.workflow_id'), '') + '_' + ISNULL(JSON_VALUE(@Event, '$.microservice_id'), ''),
                @EventProcessName = ISNULL(JSON_VALUE(@Event, '$.workflow_id'), 'Unknown'),
                @EventProcessVersionNumber = '1.0',
                @EventProcessComponentName = ISNULL(JSON_VALUE(@Event, '$.microservice_id'), 'Unknown'),
                @PeerServer = @@SERVERNAME,
                @ErrorCode = ISNULL(JSON_VALUE(@Event, '$.event_type'), 'UNKNOWN_ERROR'),
                @ErrorMessage = ISNULL(JSON_VALUE(@Event, '$.error_details'), ''),
                @ErrorDetail = ISNULL(JSON_VALUE(@Event, '$.validation_result'), ''),
                @ErrorData = ISNULL(JSON_VALUE(@Event, '$.message_content'), ''),
                @FullException = @Event,
                @ApplicationContext = NULL,
                @EventContext = @Event;
            
            -- Insert into integrationhub.Exception table
            INSERT INTO [integrationhub].[Exception] (
                [EventDateTime],
                [UniqueEventId],
                [EventProcessName],
                [EventProcessVersionNumber],
                [EventProcessComponentName],
                [PeerServer],
                [ErrorCode],
                [ErrorMessage],
                [ErrorDetail],
                [ErrorData],
                [FullException],
                [ApplicationContext],
                [EventContext]
            )
            VALUES (
                @EventDateTime,
                @UniqueEventId,
                @EventProcessName,
                @EventProcessVersionNumber,
                @EventProcessComponentName,
                @PeerServer,
                @ErrorCode,
                @ErrorMessage,
                @ErrorDetail,
                @ErrorData,
                @FullException,
                @ApplicationContext,
                @EventContext
            );
            
            -- Mark exception as processed
            INSERT INTO [queue].[ProcessedIntegrationHubException] ([IntegrationHubExceptionId], [ProcessedDateTime])
            VALUES (@ExceptionId, GETDATE());
            
        END TRY
        BEGIN CATCH
            -- Log processing error
            INSERT INTO [queue].[ExceptionProcessingError] ([IntegrationHubExceptionId], [ErrorMessage], [ErrorDateTime])
            VALUES (@ExceptionId, ERROR_MESSAGE(), GETDATE());
        END CATCH
        
        FETCH NEXT FROM exception_cursor INTO @ExceptionId, @EventCategory, @EventType, @Event, @EventXML;
    END
    
    CLOSE exception_cursor;
    DEALLOCATE exception_cursor;
END
GO