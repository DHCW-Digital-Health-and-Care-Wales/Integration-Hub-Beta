# Running the Message Replay Job Locally

> [!NOTE]
> This only applies to running it locally.

The message replay job allows you to re-send messages from the Message Store to the Service Bus priority queue. This is useful for operational support when messages need to be reprocessed.

The priority queue (`local-inthub-priority-messagequeue`) is **session-enabled**. Each replayed message is automatically stamped with the `SessionId` that was stored when the message was originally processed, so the consuming `hl7_sender` instance will pick it up without any session configuration change.

## Quick Start

1. **Initialise database**: `just start phw-to-mpi` (starts SQL Server and seeds test messages)
2. **Create replay batch**: Run `create-replay-batch.sql` in VS Code to get a `ReplayBatchId`
3. **Configure job**: Set `REPLAY_BATCH_ID` in `message-replay-job.env`
4. **Redirect sender**: Update `INGRESS_QUEUE_NAME` in the relevant sender `.env` file to `local-inthub-priority-messagequeue`
5. **Run job**: `just run replay` (builds and executes the replay job)
6. **Verify**: Check logs with `just logs message-replay-job`
7. **Revert sender**: Restore the original `INGRESS_QUEUE_NAME` in the sender `.env` file

## Quick Reference

| What You Need | Location | Notes |
|---|---|---|
| Customize which messages to replay | [sql-scripts/create-replay-batch.sql](sql-scripts/create-replay-batch.sql) | Modify the `WHERE` clause |
| Tell the job which batch to process | local/message-replay-job.env | Set `REPLAY_BATCH_ID` (required) and `REPLAY_BATCH_SIZE` (optional) |
| Verify replay succeeded | [sql-scripts/fetch-query.sql](sql-scripts/fetch-query.sql) | Empty result = success |
| View job logs while running | Terminal after `just run replay` | Or use Docker Desktop Logs tab on the message replay job container |
| View job logs after completion | `just logs message-replay-job` | Shows entire execution history |

## Prerequisites

**Before you start, verify you have:**
- Python environment set up locally (for running tests and debugging)
- A running Docker stack with SQL Server initialized (from `just start phw-to-mpi`)
- An SQL client installed (can use the VS Code extension below as well)
- VS Code with the **SQL Server (mssql)** extension installed and configured
- The `MessageStoreDB` connection configured in VS Code (see [Connecting to SQL Server from Your Machine](README.md#connecting-to-sql-server-from-your-machine))
- The `local/message-replay-job.env` file exists (should be in the repo)
- Docker Desktop is running (required for `just run replay`)

## Step 1: Initialise the Database with Test Data

Start a Docker profile to initialise the SQL Server container and populate test data:

```bash
just start phw-to-mpi
```

This command:

1. Starts the SQL Server container and initialises the `IntegrationHub` database
2. As part of DB initialisation, the `seed-messages.sql` script is run, which populates the `monitoring.Message` table with 1000 test HL7 messages. The message timestamps are distributed across multiple days to simulate real-world scenarios:
   - 25% with today's timestamp
   - 25% with yesterday's timestamp
   - 25% with tomorrow's timestamp
   - 25% with a fixed timestamp of 2025-12-31 (for testing historical message replay scenarios)

**What to watch for:**
- The terminal will show `SQL Server is now ready to accept connections` — this signals the database is ready
- Initial startup takes 20-30 seconds; the seeding happens automatically
- You can safely proceed to Step 2 once this appears

You can verify the data loaded successfully by opening your SQL client, connecting to the `MessageStoreDB`, and checking that the `monitoring.Message` table has ~1000 rows.

## Step 2: Create a Replay Batch

A replay batch groups messages that should be reprocessed together. It's a SQL operation that filters messages based on your criteria and marks them as ready for replay.

### Opening the Script

1. Open VS Code and use the **SQL Server (mssql)** extension with your `MessageStoreDB` connection
2. Open the script: [sql-scripts/create-replay-batch.sql](sql-scripts/create-replay-batch.sql)

### Understanding the Script

The script does the following:

```sql
-- Defines a unique ID for this batch
DECLARE @BatchId UNIQUEIDENTIFIER = '00000000-0000-0000-0000-000000000001';

-- Inserts messages matching your criteria into the replay queue
INSERT INTO monitoring.MessageReplayQueue
    (ReplayBatchId, MessageId)
SELECT @BatchId, Id
FROM monitoring.Message m
WHERE m.SourceSystem = '252'  -- Filter by source system (e.g., '252' = PHW)
    AND m.ReceivedAt >= DATEADD(DAY, -1, CAST(GETDATE() AS DATE))  -- Yesterday at 00:00 or later
    AND m.ReceivedAt < DATEADD(DAY, 1, CAST(GETDATE() AS DATE));   -- Before tomorrow at 00:00
```

**What this means for you:**
- `m.SourceSystem = '252'`: Only selects messages from the PHW source system. Different systems have different IDs. You can modify this to filter different sources.
- `ReceivedAt >= DATEADD(DAY, -1, ...)` (Yesterday at 00:00) and `ReceivedAt < DATEADD(DAY, 1, ...)` (Tomorrow at 00:00): This creates a date range that spans yesterday, today, and up to midnight tomorrow. The script will populate the database with default values for other columns like `Status` (set to `Pending` automatically).

### Customizing the Script for Different Scenarios

**Scenario A: Replay only messages from today**

Replace these two lines:
```sql
WHERE m.SourceSystem = '252'
    AND m.ReceivedAt >= DATEADD(DAY, -1, CAST(GETDATE() AS DATE))
    AND m.ReceivedAt < DATEADD(DAY, 1, CAST(GETDATE() AS DATE));
```

With:
```sql
WHERE m.SourceSystem = '252'
    AND m.ReceivedAt >= CAST(GETDATE() AS DATE)              -- Starting at midnight today
    AND m.ReceivedAt < DATEADD(DAY, 1, CAST(GETDATE() AS DATE));  -- Before midnight tomorrow
```

**Scenario B: Replay messages from a specific date (e.g., last Thursday, March 19)**

```sql
WHERE m.SourceSystem = '252'
    AND m.ReceivedAt >= '2026-03-19'           -- March 19, 2026 at 00:00
    AND m.ReceivedAt < '2026-03-20';           -- March 20, 2026 at 00:00
```

**Scenario C: Replay all messages from a different source system (e.g., PIMS)**

```sql
WHERE m.SourceSystem = 'PIMS'  -- Change to the PIMS source ID
    AND m.ReceivedAt >= DATEADD(DAY, -1, CAST(GETDATE() AS DATE))
    AND m.ReceivedAt < DATEADD(DAY, 1, CAST(GETDATE() AS DATE));
```

### Choosing a Batch ID

The `@BatchId` is a unique identifier for this batch. You have two options:

**Option 1: Use a hardcoded ID (current default)**
```sql
DECLARE @BatchId UNIQUEIDENTIFIER = '00000000-0000-0000-0000-000000000001';
```
Simple, but you can only create one batch at a time with this ID. Note that if you run the script again, it will add more messages to the same batch.

**Option 2: Generate a new ID each time (recommended for multiple replays)**
```sql
DECLARE @BatchId UNIQUEIDENTIFIER = NEWID();  -- Generates a fresh UUID
```
Each run creates a new, separate batch. This way you keep replays organized and prevent accidental overwrites.

### Executing the Script

1. Make any customizations you need (see scenarios above)
2. Execute the script (right-click > Execute Query, or the green play button at the top right in VS Code)
3. The script will output the `ReplayBatchId` — **copy this value** — you'll need it in Step 3

**Example output:**
```
ReplayBatchId
----------------------------------------------------
00000000-0000-0000-0000-000000000001
```

The script moved matching messages from the `monitoring.Message` table into the `monitoring.MessageReplayQueue` table and marked them with your batch ID. These messages now have a status of `Pending`, meaning they're ready to be replayed.

**To verify:** Open your SQL client and query the `monitoring.MessageReplayQueue` table. You should see rows matching your filter criteria, all with status `Pending` and the same `ReplayBatchId` you just noted.

## Step 3: Configure the Replay Job

The replay job needs to know which batch to process. Open `local/message-replay-job.env` and set the configuration.

### Required Settings

**REPLAY_BATCH_ID**

- **What it is:** The unique ID of the batch you created in Step 2
- **How to set it:** Copy the `ReplayBatchId` from the SQL script output and paste it here
- **Example:**
  ```
  REPLAY_BATCH_ID="00000000-0000-0000-0000-000000000001"
  ```
- **Important:** The job will **only** process messages with this batch ID. If you set the wrong ID, it won't process anything.
- Make sure there are no extra spaces before/after the ID

### Optional Settings

**REPLAY_BATCH_SIZE**

- **What it is:** How many messages to fetch from the database and send to Service Bus at once
- **Default:** `100`
- **How it works:**
  - With a batch size of 100, the job fetches 100 messages, sends them to Service Bus, updates the database, then repeats
  - If you have 500 messages, it will do this 5 times
- **When to change it:**
  - **Leave at 100** for typical HL7 messages (most common case)
  - **Reduce to 20 - 50** if you know messages are very large (e.g., include attachments or binary data)
  - **Increase to 200+** only if you're replaying thousands of tiny messages and want fewer database round-trips

Azure Service Bus has limits on how much data can be sent in one batch.

The underlying `MessageSenderClient.send_message_batch` automatically splits the messages you provide into one or more Service Bus batches to respect Azure Service Bus size limits. 

That means `REPLAY_BATCH_SIZE` does **not** directly guarantee that you stay under the Service Bus batch size limit; it only limits how many messages the replay job passes to the sender at a time.

If a *single* message is larger than the maximum size allowed by Service Bus, `send_message_batch` raises a `ValueError`. In this case, the replay job treats the error as unrecoverable: it marks the replay batch as **Failed** and does **not** retry it automatically.

**Example configurations:**

```bash
# Scenario 1: Standard HL7 messages (typical)
REPLAY_BATCH_SIZE=100
```

For more technical details, see [Message Replay Job README](../message_replay_job/README.md#replay_batch_size-explained).

## Step 3b: Redirect the Consuming Service to the Priority Queue

The priority queue is session-enabled. Before running the job, update **only** `INGRESS_QUEUE_NAME` in the relevant sender env file (e.g. `local/mpi-hl7-sender.env`) to point at the priority queue:

```dotenv
INGRESS_QUEUE_NAME="local-inthub-priority-messagequeue"
```

Leave `INGRESS_SESSION_ID` unchanged — each replayed message is automatically stamped with the `SessionId` stored in `monitoring.Message`, so the sender will pick up exactly the messages intended for it.

> [!IMPORTANT]
> Restart the sender container after changing the env file: `just restart <sender-service-name>`

After the replay is complete, revert `INGRESS_QUEUE_NAME` to its original value and restart again.

## Step 4: Run the Replay Job

Execute the replay job container:

```bash
just run replay
```

This command:
1. Builds a Docker container for the replay job
2. Runs it with the configuration from `message-replay-job.env`
3. Connects to the database
4. Fetches messages from your replay batch in chunks (according to `REPLAY_BATCH_SIZE`)
5. Sends each chunk to the Service Bus high-priority message queue
6. Updates the database to record progress

**Don't interrupt this process** — let it run to completion. If it fails partway through, the database will have a record of which messages were successfully sent, so you can safely re-run it.

Processing time depends on:
- Number of messages
- Message size
- Network latency to Service Bus
- System load

## Step 5: Verify the Replay Completed Successfully

Check the job logs to confirm all messages were replayed:

**Using Just:**

```bash
just logs message-replay-job
```

**Using Docker Desktop:**

1. Open Docker Desktop
2. Navigate to **Containers**
3. Select the `message-replay-job` container
4. View the **Logs** tab

**Expected output** (for a batch of 1000 messages with `REPLAY_BATCH_SIZE=100`):

```
INFO:message_replay_job.message_replay_job:Processing batch 1 for replay batch 00000000-0000-0000-0000-000000000002
INFO:message_replay_job.message_replay_job:Fetched 100 records (ReplayId range: 1-100)
INFO:message_replay_job.db_client:Updated 100 replay record(s) to status 'Loaded'
INFO:message_replay_job.message_replay_job:Batch 1: 100 records marked as Loaded
INFO:message_replay_job.message_replay_job:Processing batch 2 for replay batch 00000000-0000-0000-0000-000000000002
INFO:message_replay_job.message_replay_job:Fetched 100 records (ReplayId range: 101-200)
...
INFO:message_replay_job.message_replay_job:Processing batch 10 for replay batch 00000000-0000-0000-0000-000000000002
INFO:message_replay_job.message_replay_job:Fetched 100 records (ReplayId range: 901-1000)
INFO:message_replay_job.db_client:Updated 100 replay record(s) to status 'Loaded'
INFO:message_replay_job.message_replay_job:Batch 10: 100 records marked as Loaded
INFO:message_replay_job.message_replay_job:Processing batch 11 for replay batch 00000000-0000-0000-0000-000000000002
INFO:message_replay_job.message_replay_job:No more pending records found. Job complete.
INFO:message_replay_job.message_replay_job:Message replay job finished successfully
INFO:__main__:Message replay job completed successfully
```

If you see this output, all messages have been successfully replayed.

## Troubleshooting Common Issues

### Problem: "No rows in MessageReplayQueue table"

**Cause:** The SQL script in Step 2 didn't find any matching messages

**Solution:**
1. Double-check your `WHERE` clause filters in the SQL script
2. Verify the `SourceSystem` ID is correct for your scenario
3. Check the date range - are there actually messages in that range?
4. Try this diagnostic query in your SQL editor:
   ```sql
   SELECT DISTINCT SourceSystem, COUNT(*) as MessageCount
   FROM monitoring.Message
   GROUP BY SourceSystem
   ORDER BY MessageCount DESC
   ```
   This shows you what source systems and how many messages exist. Make sure your filter matches.

### Problem: "Job runs but MessageReplayQueue status stays Pending"

**Cause:** The replay job encountered an error and stopped processing

**Solution:**
1. Check the logs: `just logs message-replay-job` or using Docker - clicking on the replay job container > Logs tab
2. Look for error messages — they usually indicate what went wrong
3. Common errors:
   - `Connection timeout` — Service Bus unreachable (check Docker is running)
   - `Message too large` — Individual message or the overall batch exceeds Service Bus limit. 
     - First, try reducing REPLAY_BATCH_SIZE to send fewer messages at a time to narrow down which specific message(s) are failing. 
     - Once identified, the offending message must be looked into. 
     - Note that simply reducing the REPLAY_BATCH_SIZE will not make an oversized single message send successfully!
   - `Database connection failed` — Check MessageStoreDB connection
4. Once fixed, re-run `just run replay` to retry

### Problem: "REPLAY_BATCH_ID not recognized"

**Cause:** The environment variable isn't being read correctly

**Solution:**
1. Verify the file is `local/message-replay-job.env` (not `.env.local` or another variant)
2. Make sure there are no spaces around the `=` sign:
   ```bash
   # Wrong:
   REPLAY_BATCH_ID = "00000000-0000-0000-0000-000000000001"
   
   # Correct:
   REPLAY_BATCH_ID="00000000-0000-0000-0000-000000000001"
   ```
3. Rebuild the Docker image: `just run replay` which should pick up the new config

### Problem: "SQL Server connection refused"

**Cause:** The database container isn't running

**Solution:**
1. Ensure you ran `just start phw-to-mpi` in Step 1
2. Verify Docker Desktop is running
3. Check container status: `docker ps | grep sql` or in Docker under container - you should see `sqlserver`
4. If the container isn't listed, restart: `just start phw-to-mpi`

### Problem: "I accidentally used the wrong batch ID, how do I clean up the Message replay table?"

**Solution:** The `MessageReplayQueue` table can grow, so it's safe to delete batches you don't want. In your SQL editor:

```sql
DELETE FROM monitoring.MessageReplayQueue
WHERE ReplayBatchId = '00000000-0000-0000-0000-000000000001'  -- Replace with your unwanted ID
```

Then create a new batch with the correct criteria.

## How the message replay system works
The message replay system works in these phases:

1. **Batch Creation** (Step 2): You write a SQL query to filter messages from the `monitoring.Message` table based on criteria (source system, date range, etc.). These matching messages are copied to a separate `monitoring.MessageReplayQueue` table with a unique batch ID and status `Pending`.

2. **Replay Execution** (Step 4): The replay job reads messages from `MessageReplayQueue` in chunks, sends each chunk to a Service Bus queue (the same queue that processes live messages), then updates each message's status to `Loaded`.

3. **Verification** (Steps 5-6): You verify that all messages either have status `Loaded` (success) or `Failed` (error requiring investigation).

### Why Batch Processing?

We don't send all messages at once because:
- **Database efficiency:** Fetching millions of rows at once is slow. Fetching in chunks (e.g., 100 at a time) is faster.
- **Service Bus limits:** Azure Service Bus enforces message batch size limits. Sending in controlled chunks prevents rejections.
- **Observability:** You can monitor progress in real-time. If something fails, you know exactly where it stopped.

### The Role of the Status column

Messages in `MessageReplayQueue` move through statuses:
- `Pending` - Job hasn't processed this message yet
- `Loaded` - Successfully sent to Service Bus, ready for downstream processing
- `Failed` - The job tried to send but encountered an error (usually requires investigation)

### Files Involved

- **[sql-scripts/create-replay-batch.sql](sql-scripts/create-replay-batch.sql)** — SQL script you customize to define which messages to replay
- **[sql-scripts/fetch-query.sql](sql-scripts/fetch-query.sql)** — SQL script you run to verify results
- **[message-replay-job/](../message_replay_job/)** — The actual Python application for the container app job that does the replay (for reference/debugging)
- **local/message-replay-job.env** — Configuration file for the replay job (only two settings you would typically modify)

## Step 6 (Optional): Verify Unprocessed Messages

To verify what messages remain unprocessed or failed, execute the verification query:

1. Open VS Code with your `MessageStoreDB` connection
2. Open [sql-scripts/fetch-query.sql](sql-scripts/fetch-query.sql)
3. Execute the query (this shows up to 500 unprocessed/failed messages)
4. Review the results:
   - **Empty result set** - All messages in your batch have successfully been replayed (marked as `Loaded`)
   - **Rows with `Pending` status** - The job didn't process these (may indicate a crash or incomplete run)
   - **Rows with `Failed` status** - The job tried to process these but encountered an error

### Interpreting Results

**Incomplete run:**
```
ReplayBatchId | Status
00000000-0000-0000-0000-000000000001 | Pending (rows 451-500)
```
Messages 451-500 are still pending. This might mean:
- The job crashed or was interrupted
- The service bus was unreachable
- The job is still running (check Step 5 logs)

If you see this, check the logs from Step 5 to diagnose what went wrong, then re-run `just run replay` to retry.

**Failed messages:**
```
ReplayBatchId | Status
00000000-0000-0000-0000-000000000001 | Failed (rows 50, 123, 456)
```
These individual messages failed to send. Possible reasons:
- Message size exceeds Service Bus limits (very rare)
- Message format was corrupted
- Database connectivity issue during the send

You can safely re-run the job with the same batch ID to retry failed messages.
