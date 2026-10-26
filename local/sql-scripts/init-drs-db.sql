USE master;
GO

SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'DRS')
BEGIN
    CREATE DATABASE DRS;
END;
GO

USE [DRS];
GO
/****** Object:  Table [dbo].[QueueMessage]    Script Date: 26/10/2026 10:09:04 ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'QueueMessage')
BEGIN
    CREATE TABLE [dbo].[QueueMessage](
        [Id] [int] IDENTITY(1,1) NOT NULL,
        [Message] [varchar](max) NOT NULL,
        [MessageXML] [xml] NOT NULL,
        [IsPriority] [bit] NOT NULL CONSTRAINT [DF_QueueMessage_IsPriority] DEFAULT ((0)),
        CONSTRAINT [PK_QueueMessage] PRIMARY KEY CLUSTERED 
        (
            [Id] ASC
        )WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
    ) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY];
END;
GO
/****** Object:  StoredProcedure [dbo].[prQueueMessage]    Script Date: 26/10/2026 10:09:04 ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

-- =============================================
-- Author:		<Author,,Name>
-- Create date: <Create Date,,>
-- Description:	<Description,,>
-- =============================================
CREATE OR ALTER PROCEDURE [dbo].[prQueueMessage]
    @Message VARCHAR(MAX),
    @IsPriority BIT = 0
AS
BEGIN
	-- SET NOCOUNT ON added to prevent extra result sets from
	-- interfering with SELECT statements.
	SET NOCOUNT ON;

    BEGIN TRY 
        DECLARE 
             @doc XML

        -- Insert statements for procedure here
	    SET @Message = REPLACE(@Message, ' encoding="UTF-8"', '')
        SET @Message = REPLACE(@Message, '&#145;', '"')  
        SET @Message = REPLACE(@Message, '&#146;', '"')  
        SET @Message = REPLACE(@Message, '>""<','><') -- Strip out HL7 v2 NULLs represented by empty double quotes; retain in @Message
                        
        SELECT  @doc = CAST(@Message AS XML)

        INSERT INTO dbo.QueueMessage ([Message], [MessageXML], [Ispriority])
        VALUES
        (@Message, @doc, @IsPriority)

     END TRY
     BEGIN CATCH
        THROW;
     END CATCH;
END
GO
