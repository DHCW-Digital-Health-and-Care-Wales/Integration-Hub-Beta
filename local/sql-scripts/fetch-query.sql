-- Use this query to verify what messages remain unprocessed or failed.
USE IntegrationHub;
GO

WITH
    Batch
    AS
    (
        SELECT TOP (500)
            t.ReplayId, t.MessageId
        FROM monitoring.MessageReplayQueue t WITH (READPAST)
        WHERE t.Status IN ('Failed', 'Pending')
            AND t.ReplayBatchId = '00000000-0000-0000-0000-000000000001'
        ORDER BY t.ReplayId
    )
SELECT b.ReplayId, m.Id AS MessageId, m.RawPayload, m.CorrelationId
FROM Batch b
    JOIN monitoring.Message m ON m.Id = b.MessageId