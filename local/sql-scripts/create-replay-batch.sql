-- This script creates a replay batch for messages from source system '252' received between yesterday and today.
-- If using the seed-messages.sql script to generate test data, this should create a batch of 500 messages (250 from yesterday and 250 from today).

-- Adjust the date range in the where clause if you want to include different messages based on their ReceivedAt timestamps.
-- Example: m.ReceivedAt BETWEEN '2026-01-01' AND '2026-01-31'; 

-- Note: The REPLAY_BATCH_ID is hardcoded here for simplicity.
-- Use DECLARE @BatchId UNIQUEIDENTIFIER = NEWID(); instead to generate a new batch ID each time you run the script.
-- Adjust the environment variable REPLAY_BATCH_ID in local/message-replay-job.env accordingly if you change the batch ID generation method.
USE IntegrationHub;
GO

-- should match the REPLAY_BATCH_ID in local/message-replay-job.env
DECLARE @BatchId UNIQUEIDENTIFIER = '00000000-0000-0000-0000-000000000001';

INSERT INTO monitoring.MessageReplayQueue
    (ReplayBatchId, MessageId)
SELECT @BatchId, Id
FROM monitoring.Message m
WHERE m.SourceSystem = '252'
    AND m.ReceivedAt >= DATEADD(DAY, -1, CAST(GETDATE() AS DATE))
    AND m.ReceivedAt < DATEADD(DAY, 1, CAST(GETDATE() AS DATE));

SELECT @BatchId AS ReplayBatchId;