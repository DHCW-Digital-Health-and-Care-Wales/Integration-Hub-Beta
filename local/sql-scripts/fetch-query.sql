-- Use this query to verify what messages remain unprocessed or failed.
--
-- This is a manual script - it is NOT in init/, so it does not run automatically on container start.
-- Run it with:
--   docker compose exec -T postgres psql -U inthub -d integrationhub < sql-scripts/fetch-query.sql
--
-- This is a read-only inspection query, so it deliberately omits the FOR UPDATE SKIP LOCKED used
-- by the replay job itself (the T-SQL equivalent of READPAST) - running it must not take row locks
-- or hide rows the job is currently working on.

WITH batch AS (
    SELECT t.replay_id, t.message_id
    FROM monitoring.message_replay_queue t
    WHERE t.status IN ('Failed', 'Pending')
      AND t.replay_batch_id = '00000000-0000-0000-0000-000000000001'::uuid
    ORDER BY t.replay_id
    LIMIT 500
)
SELECT b.replay_id, m.id AS message_id, m.raw_payload, m.correlation_id
FROM batch b
    JOIN monitoring.message m ON m.id = b.message_id
ORDER BY b.replay_id;