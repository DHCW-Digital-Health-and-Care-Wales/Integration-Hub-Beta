#!/bin/bash
# Starts SQL Server, applies the idempotent mock schema, and only then opens port 1433.
#
# SQL Server itself listens on a loopback-only internal port. A small forwarder publishes 1433 once the
# schema exists, so "port 1433 is open" really means "DRS and dbo.prQueueMessage are ready". Without this,
# clients (and TCP health probes) can connect during startup and hit a missing database or procedure, which
# db_sender classifies as fatal and dead-letters, rather than as a transient connection failure it would retry.
set -u

SQLCMD=/opt/mssql-tools18/bin/sqlcmd
PUBLIC_PORT=1433
INTERNAL_PORT=14330
MAX_RETRIES=60
RETRY_INTERVAL=2

if [ -z "${MSSQL_SA_PASSWORD:-}" ]; then
    echo "ERROR: MSSQL_SA_PASSWORD must be set (see local/.secrets)." >&2
    exit 1
fi

MSSQL_TCP_PORT="$INTERNAL_PORT" MSSQL_IP_ADDRESS=127.0.0.1 /opt/mssql/bin/sqlservr &
SQL_PID=$!
PROXY_PID=""

# This script is PID 1, so it receives the stop signal. Forward it to SQL Server and wait for it to shut
# down cleanly, otherwise the container is killed after the grace period instead.
shutdown() {
    echo "Stop signal received, shutting down SQL Server..."
    [ -n "$PROXY_PID" ] && kill -TERM "$PROXY_PID" 2>/dev/null
    kill -TERM "$SQL_PID" 2>/dev/null
    wait "$SQL_PID"
    exit $?
}
trap shutdown TERM INT

echo "Waiting for SQL Server to accept connections..."
for attempt in $(seq 1 "$MAX_RETRIES"); do
    if "$SQLCMD" -C -S "127.0.0.1,$INTERNAL_PORT" -U sa -P "$MSSQL_SA_PASSWORD" -Q "SELECT 1" > /dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq "$MAX_RETRIES" ]; then
        echo "ERROR: SQL Server did not become ready after $MAX_RETRIES attempts." >&2
        exit 1
    fi
    sleep "$RETRY_INTERVAL"
done

echo "Applying mock DRS schema..."
if ! "$SQLCMD" -C -b -S "127.0.0.1,$INTERNAL_PORT" -U sa -P "$MSSQL_SA_PASSWORD" -d master -i /opt/mock_db_receiver/init.sql; then
    echo "ERROR: mock schema initialisation failed." >&2
    exit 1
fi

socat "TCP-LISTEN:$PUBLIC_PORT,fork,reuseaddr" "TCP:127.0.0.1:$INTERNAL_PORT" &
PROXY_PID=$!
echo "Mock DB receiver ready: database DRS, procedure dbo.prQueueMessage, listening on port $PUBLIC_PORT."

wait "$SQL_PID"
status=$?
kill -TERM "$PROXY_PID" 2>/dev/null
exit "$status"
