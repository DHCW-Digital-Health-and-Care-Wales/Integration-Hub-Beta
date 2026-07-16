-- =============================================
-- Author:       Integration Hub Team
-- Created:      2023-01-15
-- Description:  DEPRECATED — this procedure has been retired.
--               The code has been commented out.
--               Use dbo.GetActivePatients instead.
-- =============================================
CREATE OR ALTER PROCEDURE [dbo].[GetPatients_Legacy]
AS
BEGIN
    SET NOCOUNT ON;

    RAISERROR('GetPatients_Legacy is discontinued. Please use dbo.GetActivePatients.', 16, 1);

    /*
    -- Original implementation (no longer maintained):
    SELECT PatientId, NhsNumber, Forename, Surname
    FROM dbo.Patient
    WHERE IsActive = 1
    ORDER BY Surname;
    */
END;
GO

-- =============================================
-- Author:       Integration Hub Team
-- Created:      2022-11-01
-- Description:  WARNING: This procedure is no longer in use.
--               Replaced by dbo.InsertMessage.
--               Do not call this procedure.
-- =============================================
CREATE OR ALTER PROCEDURE [dbo].[StoreHL7Message_Old]
    @Payload NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;

    -- Legacy code commented out — use InsertMessage instead
    THROW 50001, 'StoreHL7Message_Old is discontinued. Use dbo.InsertMessage.', 1;

    /*
    INSERT INTO dbo.HL7MessageLog (Payload, ReceivedAt)
    VALUES (@Payload, GETDATE());
    */
END;
GO
