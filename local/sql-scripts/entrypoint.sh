#!/bin/sh

set -u

echo "Starting SQL Server..."
/opt/mssql/bin/sqlservr &
SQL_PID=$!

MAX_RETRIES=30
RETRY_INTERVAL=2
RETRY_COUNT=0

echo "Waiting for SQL Server to be ready..."

while [ "$RETRY_COUNT" -lt "$MAX_RETRIES" ]; do
    if /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "SELECT 1" >/dev/null 2>&1; then
        echo "SQL Server is ready!"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "SQL Server not ready yet. Attempt $RETRY_COUNT of $MAX_RETRIES. Retrying in $RETRY_INTERVAL seconds..."
    sleep "$RETRY_INTERVAL"
done

if [ "$RETRY_COUNT" -eq "$MAX_RETRIES" ]; then
    echo "ERROR: SQL Server failed to start after $MAX_RETRIES attempts."
    exit 1
fi

echo "Running database initialization script..."
/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d master -i /var/opt/mssql/scripts/init-db.sql

wait "$SQL_PID"
