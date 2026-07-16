-- =============================================
-- Author:       Integration Hub Team
-- Created:      2023-06-01
-- Description:  Returns patient demographics.
--               This is the legacy API layer — use dbo.GetActivePatients instead.
-- =============================================
CREATE OR ALTER PROCEDURE [api].[GetPatient]
    @NhsNumber NVARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;

    -- Retained temporarily for backwards compatibility.
    -- Replacement: dbo.GetActivePatients
    SELECT
        p.PatientId,
        p.NhsNumber,
        p.Forename,
        p.Surname
    FROM dbo.Patient p
    WHERE p.NhsNumber = @NhsNumber;
END;
GO

-- =============================================
-- Author:       Integration Hub Team
-- Created:      2023-06-15
-- Description:  Creates an admission record via the legacy API schema.
--               Migrated to dbo.CreateAdmission. Do not use this procedure.
-- =============================================
CREATE OR ALTER PROCEDURE [api].[CreateAdmission]
    @PatientId INT,
    @WardId    INT
AS
BEGIN
    SET NOCOUNT ON;

    -- New procedure: dbo.CreateAdmission
    INSERT INTO dbo.Admission (PatientId, WardId, AdmittedAt)
    VALUES (@PatientId, @WardId, SYSUTCDATETIME());
END;
GO
