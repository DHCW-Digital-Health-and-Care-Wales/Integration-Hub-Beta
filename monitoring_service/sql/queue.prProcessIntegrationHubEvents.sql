SET QUOTED_IDENTIFIER ON
GO
SET ANSI_NULLS ON
GO

-- Integration Hub Event Processing Procedure
CREATE PROCEDURE [queue].[prProcessIntegrationHubEvents] @BatchSize INT
AS
    BEGIN

        SET NOCOUNT ON;
        SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
      
	  --DECLARE  @BatchSize INT = 1

        SELECT TOP (@BatchSize)
               Q.[IntegrationHubEventId]
        INTO   #TheEventIDs
        FROM
               [queue].[IntegrationHubEvent] Q WITH (NOLOCK)
        ORDER BY
               Q.[IntegrationHubEventId] ASC;


        IF (EXISTS (SELECT TOP 1 IntegrationHubEventId FROM #TheEventIDs))
            BEGIN

                DECLARE
                    @rowcount                   INT
                  , @EventDateTime             DATETIME2(0)
                  , @UniqueEventId             VARCHAR(800)
                  , @EventProcessName          VARCHAR(800)
                  , @EventProcessVersionNumber VARCHAR(25)
                  , @EventProcessComponentName VARCHAR(800)
                  , @PeerServer                VARCHAR(256)
                  , @EventPayload              VARCHAR(MAX)
                  , @ApplicationContext        VARCHAR(MAX)
                  , @EventContext              VARCHAR(MAX)
                  , @StartProcessingDateTime   DATETIME2(0)
                 -- , @EndProcessingDateTime     DATETIME2(0)
                  , @UpdatedStatus              CHAR(1);
				
				DECLARE @Hdoc INT;
                
				CREATE TABLE #BatchToProcess
                    (
                        [IntegrationHubEventId] BIGINT       NOT NULL
                      , [EventXML]       XML          NULL
					  , [EventMessage] VARCHAR(max)
                      , [EventType]      VARCHAR(256) NULL
					  , [InsertedDateTime] [DATETIME2](0) NOT NULL,
                    );

                DECLARE @logtable TABLE
                    (
                        [IntegrationHubEventId] INT           IDENTITY(0, 1) NOT NULL
                      , [LogDateTime]    DATETIME      NULL
                      , [StoredProcName] VARCHAR(500)  NULL
                      , [LogStatus]      VARCHAR(2)    NULL
                      , [LogEntry]       VARCHAR(1000) NULL
                    );

                INSERT INTO #BatchToProcess
                    (
                        [IntegrationHubEventId]
                      , [EventXML]
					  , [EventMessage]
                      , [EventType]
					  , [InsertedDateTime]
                    )
                            SELECT  
                                    Q.[IntegrationHubEventId]
                                  , TRY_CAST(REPLACE(Q.[Event], '<?xml version="1.0" encoding="UTF-8"?>', '') AS XML)
								  , Q.[Event]
                                  , Q.EventType
								  , Q.[InsertedDateTime]
                            FROM [queue].[IntegrationHubEvent] Q WITH (NOLOCK)
                            INNER JOIN #TheEventIDs AS I
                                        ON I.[IntegrationHubEventId] = Q.[IntegrationHubEventId];

                --Check how many rows were just picked up, if none were then we can exit right here. 
                SET @rowcount = @@ROWCOUNT;

                INSERT INTO @logtable
                            SELECT
                                GETDATE ()
                              , NULL --OBJECT_NAME (@@PROCID)
                              , 'OK'
                              , 'Step 1 - Number of Events to process: ' + CAST (@rowcount AS VARCHAR(255));

                IF (@rowcount > 0)
                    BEGIN
                       
					  DECLARE
                            @IntegrationHubEventId        BIGINT
                          , @EventType VARCHAR(256)
                          , @EventXML  XML
						  , @EventMessage VARCHAR(MAX)
						  , @InsertedDateTime [DATETIME2](0) ;
                   
				   WHILE ((SELECT COUNT (*) FROM  #BatchToProcess) > 0)
                      BEGIN
                           
						   SET @StartProcessingDateTime = GETDATE ();

						   SELECT TOP 1
                                      @IntegrationHubEventId   = b.[IntegrationHubEventId]
                                    , @EventType		= b.[EventType]
                                    , @EventXML			= b.[EventXML]
									, @EventMessage		= B.EventMessage
									, @InsertedDateTime = b.[InsertedDateTime]
                            FROM
                                    #BatchToProcess b;
						
                            BEGIN TRY
							  BEGIN 
                               

                                INSERT INTO @logtable
                                    SELECT
                                        GETDATE ()
                                        , NULL --OBJECT_NAME (@@PROCID)
                                        , 'OK'
                                        , 'Step 2.0 - Processing Event Row Id: ' + CAST (@IntegrationHubEventId AS VARCHAR(25));
									
									
									EXEC sys.sp_xml_preparedocument @Hdoc OUTPUT,
																	@EventXML;

									SELECT 
									 @EventDateTime					= EventDateTime				
								    ,@UniqueEventId					= UniqueEventId				
								    ,@EventProcessName				= EventProcessName			
								    ,@EventProcessVersionNumber		= EventProcessVersionNumber	
								    ,@EventProcessComponentName		= EventProcessComponentName	
								    ,@PeerServer					= PeerServer				
								    ,@EventPayload					= EventPayload				
								    ,@ApplicationContext			= ApplicationContext		
								    ,@EventContext					= EventContext
										FROM OPENXML(@Hdoc, 'IntegrationHubEvent')
											WITH (												
													EventDateTime				DATETIME2(0)	'EventData/EventGenerationDate',
													UniqueEventId				VARCHAR(500)	'EventData/WorkflowInstanceId',																								
													EventProcessName			VARCHAR(500)	'EventProcess/Name',
													EventProcessVersionNumber	VARCHAR(50)		'EventProcess/Version',
													EventProcessComponentName	VARCHAR(500)	'EventProcess/Component',
													PeerServer					VARCHAR(500)	'EventData/PeerServer',
													EventPayload				VARCHAR(max)	'EventMessage/Payload',
													ApplicationContext			VARCHAR(MAX)	'EventMessage/ApplicationContext',
													EventContext				VARCHAR(max)	'EventMessage/CarryForwardContext'
											);

			                   		EXEC sys.sp_xml_removedocument @Hdoc;
									
									
									DECLARE @EventPayloadXML XML;
									SET @EventPayloadXML = TRY_CAST(REPLACE(@EventPayload, '<?xml version="1.0" encoding="UTF-8"?>', '') AS XML);

						
						
						BEGIN TRAN
						
						INSERT INTO [IntegrationHub].[Event]
							(
								[EventDateTime]
							  , [UniqueEventId]
							  , [EventProcessName]
							  , [EventProcessVersionNumber]
							  , [EventProcessComponentName]
							  , [PeerServer]
							  , [EventMessage]
							  , [EventMessageXML]
							  , [ApplicationContext]
							  , [EventContext]
							)
						VALUES
							(
								@EventDateTime, @UniqueEventId, @EventProcessName, @EventProcessVersionNumber, @EventProcessComponentName, @PeerServer, @EventMessage
							  , @EventPayloadXML, @ApplicationContext, @EventContext
							);					

					/*
					1. Add process to insert record in to the [queue].[EventExceptions] table where the Workflow and Componnents combination matches to the 
					setting table [Queue].[EventExceptionsSettings] records
					2. Process data from [queue].[EventExceptions] table to see if the Specified Error/Exception code included in the XML then proceed to set Alert as directed					
					
					

					DECLARE @EventExceptionsSettingID INT = 0;

					SELECT TOP 1 @EventExceptionsSettingID = [EventExceptionsSettingID]  FROM [INSE_Event].[IntegrationHub].[EventExceptionsSettings] AS ee
							WHERE ee.[EventProcessName] = @EventProcessName
								AND ee.[EventProcessComponentName] = @EventProcessComponentName

					IF(@EventExceptionsSettingID > 0)
					BEGIN
						INSERT INTO [queue].[EventExceptions]
						   (
						       [InsertedDateTime]
							  ,[EventDateTime]
							  ,[EventProcessName]
							  ,[EventProcessComponentName]
							  ,[EventMessage]
							)
					 VALUES
						   (
							   GETDATE(),
							   @EventDateTime, 
							   @EventProcessName, 
							   @EventProcessComponentName, 
							   @EventMessage
							)
					END 
					*/

						DELETE 						
						FROM [queue].[IntegrationHubEvent]
						OUTPUT deleted.IntegrationHubEventId, deleted.[EventCategory] ,deleted.[EventType] ,deleted.[Event] 
									,deleted.[InsertedDateTime],deleted.[EventXML], @StartProcessingDateTime, GETDATE()
									INTO [archive].[IntegrationHubEvent]
						WHERE IntegrationHubEventId = @IntegrationHubEventId;
						
					
							
						COMMIT TRAN											

                        INSERT INTO @logtable
                            SELECT
                                GETDATE ()
                                , NULL --OBJECT_NAME (@@PROCID)
                                , 'OK'
                                , 'Step 3.0 - Event Row Id ' + CAST (@IntegrationHubEventId AS VARCHAR(25)) + ' The Event record has been inserted in to the table IntegrationHub.Event';

								END 
                                END TRY
                                BEGIN CATCH
									BEGIN 
									ROLLBACK TRAN

                                    DECLARE
                                        @errornumber    INT
                                        = ERROR_NUMBER ()
                                      , @errorseverity  INT            = ERROR_SEVERITY ()
                                      , @errorstate     INT            = ERROR_STATE ()
                                      , @errorprocedure NVARCHAR(128)  = ISNULL (ERROR_PROCEDURE (), 'Not Defined')
                                      , @errorline      INT            = ERROR_LINE ()
                                      , @errormessage   NVARCHAR(4000) = OBJECT_SCHEMA_NAME (@@PROCID) + N'.' + OBJECT_NAME (@@PROCID) + N': ' + ERROR_MESSAGE ()
                                                                         + N' (Queue Id: ' + CAST  (@IntegrationHubEventId AS VARCHAR(25)) + N' )'
                                      , @errorpayload   VARBINARY(MAX) = CAST( (
                                                                                                      SELECT
                                                                                                          *
                                                                                                      FROM
                                                                                                          @logtable
                                                                                                      FOR JSON PATH, ROOT('ErrorPayload')
                                                                                                  ) AS VARBINARY(MAX)
                                                                                 );

                                    DECLARE @ErrorNumberTable AS TABLE ( ErrorID bigint);
									DECLARE @ErrorID BIGINT;

									INSERT INTO [log].[Error]
										
										(
											[ErrorNumber]
										  , [ErrorSeverity]
										  , [ErrorState]
										  , [ErrorProcedure]
										  , [ErrorLine]
										  , [ErrorMessage]
										  , [Payload]
										
										)
									OUTPUT inserted.Id INTO @ErrorNumberTable
									VALUES
										(
											@ErrorNumber
											, @ErrorSeverity
											, @ErrorState
											, @ErrorProcedure
											, @ErrorLine
											, @ErrorMessage
											, @errorpayload
										);
								   
								   SELECT TOP 1 
									@ErrorID = ErrorID
								   FROM @ErrorNumberTable

								   DELETE 						
									FROM [queue].[IntegrationHubEvent]
									OUTPUT deleted.IntegrationHubEventId, deleted.[EventCategory] ,deleted.[EventType] ,deleted.[Event] 
												,deleted.[InsertedDateTime],deleted.[EventXML], @StartProcessingDateTime, GETDATE(), @ErrorID
												INTO [archive].[IntegrationHubEventErrors]
									WHERE IntegrationHubEventId = @IntegrationHubEventId
								
								----TODO Insert error details
                                    --EXEC [log].[prInsertError]
                                    --    @ErrorNumber = @errornumber       -- int
                                    --  , @ErrorSeverity = @errorseverity   -- int
                                    --  , @ErrorState = @errorstate         -- int
                                    --  , @ErrorProcedure = @errorprocedure -- nvarchar(128)
                                    --  , @ErrorLine = @errorline           -- int
                                    --  , @ErrorMessage = @errormessage     -- nvarchar(4000)
                                    --  , @Payload = @errorpayload;         -- varbinary(max)

                                  END 
								END CATCH;

                                DELETE FROM
                                #BatchToProcess
                                WHERE
                                    IntegrationHubEventId = @IntegrationHubEventId;

                            END; --End of loop

                        DECLARE @event VARCHAR(MAX) =
                                    (
                                        SELECT
                                            *
                                        FROM
                                            @logtable
                                        FOR JSON PATH, ROOT('IntegrationHubEventProcessing')
                                    ); -- nvarchar(max)


                        EXEC [log].[prInsertNewEventLog]
                            @EventType = N'IntegrationHubEventProcessing' -- nvarchar(100)
                          , @Event = @event;
                    END;
                DROP TABLE IF EXISTS #BatchToProcess;
            END;
        ELSE
            BEGIN
                PRINT 'No Events Found, Exiting.';
            END;

        DROP TABLE IF EXISTS #TheEventIDs;
    END;
GO
