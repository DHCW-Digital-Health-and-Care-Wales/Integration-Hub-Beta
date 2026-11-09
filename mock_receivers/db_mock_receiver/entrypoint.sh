#!/bin/bash
# Starts SQL Server, applies the idempotent mock schema once it accepts connections, then stays in the foreground.
set -u

SQLCMD=/opt/mssql-tools18/bin/sqlcmd
MAX_RETRIES=60
RETRY_INTERVAL=2

if [ -z "${MSSQL_SA_PASSWORD:-}" ]; then
    echo "ERROR: MSSQL_SA_PASSWORD must be set (see local/.secrets)." >&2
    exit 1
fi

/opt/mssql/bin/sqlservr &
SQL_PID=$!

# This script is PID 1, so it receives the stop signal. Forward it to SQL Server and wait for it to shut
# down cleanly, otherwise the container is killed after the grace period instead.
shutdown() {
    echo "Stop signal received, shutting down SQL Server..."
    kill -TERM "$SQL_PID" 2>/dev/null
    wait "$SQL_PID"
    exit $?
}
trap shutdown TERM INT

echo "Waiting for SQL Server to accept connections..."
for attempt in $(seq 1 "$MAX_RETRIES"); do
    if "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "SELECT 1" > /dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq "$MAX_RETRIES" ]; then
        echo "ERROR: SQL Server did not become ready after $MAX_RETRIES attempts." >&2
        exit 1
    fi
    sleep "$RETRY_INTERVAL"
done

echo "Applying mock DRS schema..."
if ! "$SQLCMD" -C -b -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d master -i /opt/mock_db_receiver/init.sql; then
    echo "ERROR: mock schema initialisation failed." >&2
    exit 1
fi
echo "Mock DB receiver ready: database DRS, procedure dbo.prQueueMessage."

wait "$SQL_PID"
