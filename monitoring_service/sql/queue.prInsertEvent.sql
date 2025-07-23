SET QUOTED_IDENTIFIER ON
GO
SET ANSI_NULLS ON
GO

-- Integration Hub Event Insertion Procedure
CREATE PROCEDURE [queue].[prInsertEvent]
	@EventCategory [VARCHAR](256), @EventType VARCHAR(256), @Event VARCHAR(MAX)
AS
BEGIN

	SET NOCOUNT ON;
	DECLARE @EventXML XML;

    --SET @EventXML = TRY_CAST(@Event AS XML)
	--SET @EventXML = TRY_CAST( CONVERT(NVARCHAR(MAX),REPLACE(@Event,'UTF-8','UTF-16')) AS XML)

	SET @EventXML = TRY_CAST(REPLACE(@Event, '<?xml version="1.0" encoding="UTF-8"?>', '') AS XML)

	BEGIN TRY
    
		IF(@EventType = 'FESB-I01')
			BEGIN 
					INSERT INTO [queue].[IntegrationHubEvent]
						   ([EventCategory]
						   ,[EventType]
						   ,[Event]
						   ,[InsertedDateTime]
						   ,[EventXML])
					 VALUES
						   (
							@EventCategory
						   ,@EventType
						   ,@Event
						   ,GETDATE()
						   ,@EventXML)
					   
					INSERT INTO [queue].[IntegrationHubReport]
						   ([EventCategory]
						   ,[EventType]
						   ,[Event]
						   ,[InsertedDateTime]
						   ,[EventXML])
					 VALUES
						   (
							@EventCategory
						   ,@EventType
						   ,@Event
						   ,GETDATE()
						   ,@EventXML)
			
			END 
		ELSE IF(@EventType = 'FESB-E01')
			BEGIN 
					INSERT INTO [queue].[IntegrationHubException]
							   ([EventCategory]
							   ,[EventType]
							   ,[Event]
							   ,[InsertedDateTime]
							   ,[EventXML])
						 VALUES
							   (
								@EventCategory
							   ,@EventType
							   ,@Event
							   ,GETDATE()
							   ,@EventXML)
					   				
			END
		ELSE 
			BEGIN 
				INSERT INTO [queue].[Event]
						([EventCategory]
						,[EventType]
						,[Event]
						,[InsertedDateTime]
						,[EventXML])
					VALUES
						(
						@EventCategory
						,@EventType
						,@Event
						,GETDATE()
						,@EventXML)
					   				
			END
	END TRY
	BEGIN CATCH
		BEGIN TRY	
			INSERT INTO [queue].[Event]
				   ([InsertedDateTIme]
				   ,[EventCategory]
				   ,[EventType]
				   ,[Status]
				   ,[Event]
				   ,[EventXML])
			 VALUES
				   (GETDATE()
				   ,@EventCategory
				   ,@EventType
				   ,'E'
				   ,@Event
				   ,NULL)
		END TRY 
		BEGIN CATCH
			 INSERT INTO [log].[Error]
                (
                    [InsertedDateTime]
                  , [ErrorNumber]
                  , [ErrorSeverity]
                  , [ErrorState]
                  , [ErrorProcedure]
                  , [ErrorLine]
                  , [ErrorMessage]
                  , [Payload]
                )
            VALUES
                (
                    GETDATE (), ERROR_NUMBER (), ERROR_SEVERITY (), ERROR_STATE (), ERROR_PROCEDURE (), ERROR_LINE ()
                  , OBJECT_SCHEMA_NAME (@@PROCID) + N'.' + OBJECT_NAME (@@PROCID) + N': ' + ERROR_MESSAGE (), CONVERT(VARBINARY(max), ' EventCategory : '+@EventCategory+ ' EventType : '+ @EventType+ ' Event : ' +@Event)
                );
	
		END CATCH
	END CATCH
END
GO
