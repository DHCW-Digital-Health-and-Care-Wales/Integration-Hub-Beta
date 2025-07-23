SET QUOTED_IDENTIFIER ON
GO
SET ANSI_NULLS ON
GO

-- Integration Hub Exception Processing Procedure
CREATE PROCEDURE [queue].[prProcessIntegrationHubException]
     @BatchSize INT
AS
    BEGIN

        SET NOCOUNT ON;
		SET XACT_ABORT ON
		SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

                DECLARE @IntegrationHubExceptionId        BIGINT
                DECLARE @EventXML				   XML
				DECLARE @EventMessage			   VARCHAR(MAX)
                DECLARE @EventDateTime             DATETIME2(0)
                DECLARE @UniqueEventId             VARCHAR(800)
                DECLARE @EventProcessName          VARCHAR(800)
                DECLARE @EventProcessVersionNumber VARCHAR(25)
                DECLARE @EventProcessComponentName VARCHAR(800)
                DECLARE @PeerServer                VARCHAR(256)
                DECLARE @EventPayload              VARCHAR(MAX)
                DECLARE @ApplicationContext        VARCHAR(MAX)
                DECLARE @EventContext              VARCHAR(MAX)
                DECLARE @StartProcessingDateTime   DATETIME2(0)	
				DECLARE @ExceptionPayload			VARCHAR(MAX);
				DECLARE @ErrorCode					VARCHAR(MAX);
				DECLARE @ErrorMessage				VARCHAR(MAX);
				DECLARE @ErrorDetail				VARCHAR(MAX);
				DECLARE @ErrorData					VARCHAR(MAX);
				DECLARE @Errorpayload				VARBINARY(MAX); 
				DECLARE @rowcount					INT = 0
				DECLARE @Hdoc INT;

       WHILE(@BatchSize > @rowcount) 
		BEGIN
				SET @IntegrationHubExceptionId = 0;
				SET @EventXML = NULL;

			SELECT  TOP (1)
                    @IntegrationHubExceptionId = Q.[IntegrationHubExceptionId]
                    ,@EventXML =  Q.EventXML
            FROM [queue].[IntegrationHubException] Q WITH (NOLOCK)
			ORDER BY [IntegrationHubExceptionId] ASC
	 
			IF( @IntegrationHubExceptionId > 0 )
			BEGIN   
				SET @Hdoc = 0;
				SET @StartProcessingDateTime = SYSDATETIME();

                            BEGIN TRY
                                BEGIN 

									EXEC sys.sp_xml_preparedocument @Hdoc OUTPUT,
																	@EventXML;

									SELECT TOP 1
										@ExceptionPayload				= EventPayload
									,	@EventDateTime					= EventDateTime				
								    ,	@UniqueEventId					= UniqueEventId				
								    ,	@EventProcessName				= EventProcessName			
								    ,	@EventProcessVersionNumber		= EventProcessVersionNumber	
								    ,	@EventProcessComponentName		= EventProcessComponentName	
								    ,	@PeerServer						= PeerServer				
								    ,	@EventPayload					= EventPayload				
								    ,	@ApplicationContext				= ApplicationContext		
								    ,	@EventContext					= EventContext
										FROM OPENXML(@Hdoc, 'IntegrationHubEvent')
											WITH (	
													EventPayload				VARCHAR(max)	'EventMessage/Payload',
													EventDateTime				DATETIME2(0)	'EventData/EventGenerationDate',
													UniqueEventId				VARCHAR(500)	'EventData/WorkflowInstanceId',																								
													EventProcessName			VARCHAR(500)	'EventProcess/Name',
													EventProcessVersionNumber	VARCHAR(50)		'EventProcess/Version',
													EventProcessComponentName	VARCHAR(500)	'EventProcess/Component',
													PeerServer					VARCHAR(500)	'EventData/PeerServer',
													ApplicationContext			VARCHAR(MAX)	'EventMessage/ApplicationContext',
													EventContext				VARCHAR(max)	'EventMessage/CarryForwardContext'
											);

								EXEC sys.sp_xml_removedocument @Hdoc;
								
								SET  @ExceptionPayload	 = REPLACE(@ExceptionPayload , 'ns1:','') 
                   				SET  @Hdoc = 0;
								
								EXEC sys.sp_xml_preparedocument @Hdoc OUTPUT, @ExceptionPayload;
					
								SELECT TOP (1)
										@ErrorCode						= errorCode
									,	@ErrorMessage					= errorMessage
									,	@ErrorDetail					= errorDetail
									,	@ErrorData						= Thedata						
								FROM OPENXML(@Hdoc, 'Error')
									WITH (	

											errorCode					VARCHAR(500)	'errorCode',
											errorMessage				VARCHAR(max)	'errorMessage',
											errorDetail					VARCHAR(max)	'errorDetail',
											Thedata						VARCHAR(max)	'data'
									);
								EXEC sys.sp_xml_removedocument @Hdoc;
								SET  @Hdoc = 0;

                   		BEGIN TRAN
						
						INSERT INTO [IntegrationHub].[Exception]
							(
								[EventDateTime]
							  , [UniqueEventId]
							  , [EventProcessName]
							  , [EventProcessVersionNumber]
							  , [EventProcessComponentName]
							  , [PeerServer]
							  , [ErrorCode]
							  , [ErrorMessage]
							  , [ErrorDetail]
							  , [ErrorData]
							  , [FullException]
							  , [ApplicationContext]
							  , [EventContext]
							)
						VALUES
							(
								  @EventDateTime
								, @UniqueEventId
								, @EventProcessName
								, @EventProcessVersionNumber
								, @EventProcessComponentName
								, @PeerServer
								, @ErrorCode
								, @ErrorMessage 
								, @ErrorDetail 
								, @ErrorData
								, @EventMessage
								, @ApplicationContext
								, @EventContext
							);
						--COMMIT TRAN	

						--BEGIN TRAN
							DELETE 						
							FROM [queue].[IntegrationHubexception]
							OUTPUT 
								  deleted.[IntegrationHubExceptionId]
								, deleted.[EventCategory] 
								, deleted.[EventType] 
								, deleted.[Event] 
								, deleted.[InsertedDateTime]
								, deleted.[EventXML]
								, @StartProcessingDateTime
								, SYSDATETIME()
								INTO [archive].[IntegrationHubException]
							WHERE [IntegrationHubExceptionId] = @IntegrationHubExceptionId
							
						COMMIT TRAN															
					  END 
                    END TRY
                    BEGIN CATCH
						BEGIN 
							IF(@@TRANCOUNT > 0)
								BEGIN
									ROLLBACK TRAN  
								END

							
								DECLARE @errornumber    INT				 = ERROR_NUMBER ()
								DECLARE @errorseverity  INT            = ERROR_SEVERITY ()
								DECLARE @errorstate     INT            = ERROR_STATE ()
								DECLARE @errorprocedure NVARCHAR(128)  = ISNULL (ERROR_PROCEDURE (), 'Not Defined')
								DECLARE @errorline      INT            = ERROR_LINE ()
								SET @errormessage				   = OBJECT_SCHEMA_NAME (@@PROCID) + N'.' + OBJECT_NAME (@@PROCID) + N': ' + ERROR_MESSAGE ()
																	+ N' (Queue Id: ' + CAST  (@IntegrationHubExceptionId AS VARCHAR(25)) + N' )'

							DECLARE @ErrorNumberTable AS TABLE (ErrorID bigint);
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
							FROM [queue].[IntegrationHubException]
							OUTPUT 
									deleted.IntegrationHubExceptionId
								, deleted.[EventCategory] 
								, deleted.[EventType] 
								, deleted.[Event] 
								, deleted.[InsertedDateTime]
								, deleted.[EventXML]
								, @StartProcessingDateTime
								, GETDATE()
								,@ErrorID
							INTO [archive].[IntegrationHubExceptionErrors]
							WHERE IntegrationHubExceptionId = @IntegrationHubExceptionId

						END 
                    END CATCH;
                            END; --End of loop

				SET @rowcount = @rowcount + 1;
              END;

    END;
GO
