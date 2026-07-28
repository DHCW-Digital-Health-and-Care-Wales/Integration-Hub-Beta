-- This script creates a replay batch for messages from source system '252' received between yesterday and today.
-- If using the seed data in init/02-seed-messages.sql, this should create a batch of 500 messages
-- (250 from yesterday and 250 from today).
--
-- This is a manual script - it is NOT in init/, so it does not run automatically on container start.
-- Run it with:
--   docker compose exec -T postgres psql -U inthub -d integrationhub < sql-scripts/create-replay-batch.sql
--
-- Adjust the date range in the WHERE clause to include different messages based on their received_at timestamps.
-- Example: m.received_at BETWEEN '2026-01-01' AND '2026-01-31'
--
-- Note: the batch ID is hardcoded here for simplicity, and must match REPLAY_BATCH_ID in
-- local/message-replay-job.env. Use gen_random_uuid() instead if you want a new batch ID each
-- run, and update the env file accordingly.
--
-- Date maths is done in UTC to match how received_at is stored. The T-SQL version used the
-- server's local GETDATE(), which drifted from the stored UTC values during BST.

INSERT INTO monitoring.message_replay_queue
    (replay_batch_id, message_id)
SELECT '00000000-0000-0000-0000-000000000001'::uuid, m.id
FROM monitoring.message m
WHERE m.source_system = '252'
  AND m.received_at >= (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') - interval '1 day'
  AND m.received_at < (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') + interval '1 day';

SELECT '00000000-0000-0000-0000-000000000001'::uuid AS replay_batch_id;