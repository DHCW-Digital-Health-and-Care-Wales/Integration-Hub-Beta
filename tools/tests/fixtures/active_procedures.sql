-- =============================================
-- Author:       Integration Hub Team
-- Created:      2024-03-01
-- Description:  Returns a list of active patients currently admitted
--               to a ward, filtered by source system.
-- =============================================
CREATE OR ALTER PROCEDURE [dbo].[GetActivePatients]
    @SourceSystem NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        p.PatientId,
        p.NhsNumber,
        p.Forename,
        p.Surname,
        a.AdmittedAt,
        w.WardName
    FROM dbo.Patient p
    INNER JOIN dbo.Admission a ON a.PatientId = p.PatientId
    INNER JOIN dbo.Ward w ON w.WardId = a.WardId
    WHERE a.DischargedAt IS NULL
      AND p.SourceSystem = @SourceSystem;
END;
GO

-- =============================================
-- Author:       Integration Hub Team
-- Created:      2024-04-10
-- Description:  Inserts a new message into the monitoring store.
--               Used by the message store service.
-- =============================================
CREATE OR ALTER PROCEDURE [dbo].[InsertMessage]
    @CorrelationId   NVARCHAR(100),
    @SourceSystem    NVARCHAR(100),
    @RawPayload      NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO monitoring.Message
        (ReceivedAt, StoredAt, CorrelationId, SourceSystem, ProcessingComponent, RawPayload, SessionId)
    VALUES
        (SYSUTCDATETIME(), SYSUTCDATETIME(), @CorrelationId, @SourceSystem, 'MessageStoreService', @RawPayload, NEWID());
END;
GO

-- =============================================
-- Author:       Integration Hub Team
-- Created:      2024-04-10
-- Description:  Fetches messages for replay from the MessageReplayQueue.
--               Called by the message replay job.
-- =============================================
CREATE OR ALTER PROCEDURE [dbo].[GetPendingReplayMessages]
    @BatchId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        q.ReplayId,
        q.MessageId,
        m.RawPayload,
        m.CorrelationId,
        m.SourceSystem
    FROM monitoring.MessageReplayQueue q
    INNER JOIN monitoring.Message m ON m.Id = q.MessageId
    WHERE q.ReplayBatchId = @BatchId
      AND q.Status IN ('Pending', 'Failed')
    ORDER BY q.ReplayId;
END;
GO
