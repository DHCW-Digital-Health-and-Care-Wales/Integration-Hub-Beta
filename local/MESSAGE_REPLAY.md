# Running the Message Replay Job

The message replay job allows you to re-send messages from the Message Store to the Service Bus priority queue. This is useful for operational support when messages need to be reprocessed.

## Quick Start

1. **Initialise database**: `just start phw-to-mpi` (starts SQL Server and seeds test messages)
2. **Create replay batch**: Run `create-replay-batch.sql` in VS Code to get a `ReplayBatchId`
3. **Configure job**: Set `REPLAY_BATCH_ID` in `message-replay-job.env`
4. **Run job**: `just run replay` (builds and executes the replay job)
5. **Verify**: Check logs with `just logs message-replay-job`

## Prerequisites

- A running Docker stack with at least the SQL Server service initialised
- The `MessageStoreDB` connection configured in VS Code (see [Connecting to SQL Server from Your Machine](README.md#connecting-to-sql-server-from-your-machine))
- Python environment set up locally (for running tests and debugging)

## Step 1: Initialise the Database with Test Data

Start a Docker profile to initialise the SQL Server container and populate test data:

```bash
just start phw-to-mpi
```

This command:

1. Starts the SQL Server container and initialises the `IntegrationHub` database
2. As part of DB initialisation, the `seed-messages.sql` script is run, which populates the `monitoring.Message` table with 1000 test HL7 messages. The message timestamps are distributed across multiple days:
   - 25% with today's timestamp
   - 25% with yesterday's timestamp
   - 25% with tomorrow's timestamp
   - 25% with a fixed timestamp of 2025-12-31 (for testing date range queries)

Wait for the containers to fully initialise before proceeding.

## Step 2: Create a Replay Batch

A replay batch groups messages that should be reprocessed together. Create one using the `create-replay-batch.sql` script:

1. Open VS Code and use the **SQL Server (mssql)** extension with your `MessageStoreDB` connection
2. Open the script at `local/sql-scripts/create-replay-batch.sql`
3. Review the script comments at the top — the `REPLAY_BATCH_ID` is currently hardcoded as `00000000-0000-0000-0000-000000000001`. You have two options:
   - **Use the hardcoded ID**: Execute the script as-is and it will use the default batch ID
   - **Generate a new ID each time**: Modify line 14 to use `DECLARE @BatchId UNIQUEIDENTIFIER = NEWID();` instead of the hardcoded value. This generates a unique batch ID on each run.
4. Execute the script (keyboard shortcut or right-click > Execute Query or the green play button at the top right)
5. The script will create a new replay batch and output the `ReplayBatchId` (a UUID). Note this ID — you'll use it in the next step.

> **Note**: The `create-replay-batch.sql` script automatically moves all pending messages which match the SQL query from the `monitoring.Message` table into the `monitoring.MessageReplayQueue` table, marking them with a unique `ReplayBatchId`.

## Step 3 (Optional): Customise Replay Job Configuration

Open `local/message-replay-job.env` and adjust the configuration:

**REPLAY_BATCH_ID** (Required)

- Set this to the `ReplayBatchId` returned by `create-replay-batch.sql`
- Example: `REPLAY_BATCH_ID="00000000-0000-0000-0000-000000000002"`
- **The job only processes messages belonging to this batch**

**REPLAY_BATCH_SIZE** (Optional)

- Default: `100` — controls how many messages are fetched from the database per round-trip
- Trade-offs:
  - **Smaller sizes** (10–50): More database round-trips, finer progress granularity
  - **Larger sizes** (200–500): Fewer round-trips, coarser progress reporting, larger failure impact
- For typical HL7 message sizes, 100 is a good balance and prevents Service Bus batch splitting (which can increase duplication risk). Increase only if you're replaying very large batches and want to minimize DB queries.
- For more information: See the [Message Replay Job README](../message_replay_job/README.md#replay_batch_size-explained)

## Step 4: Run the Replay Job

Execute the replay job container:

```bash
just run replay
```

This command builds and runs the `message-replay-job` container app with the configuration from `message-replay-job.env`.

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

## Step 6 (Optional): Verify Unprocessed Messages

To verify what messages remain unprocessed or failed, execute the `fetch-query.sql` script:

1. Open VS Code with your `MessageStoreDB` connection
2. Open `local/sql-scripts/fetch-query.sql`
3. Execute the query
4. The result will show any messages that are still in `Pending` or `Failed` status (i.e., not yet replayed or failed during replay)

If the result set is empty, all messages were successfully replayed.
