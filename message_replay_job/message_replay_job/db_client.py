import logging
from types import TracebackType
from typing import List

import pyodbc

from .replay_record import ReplayRecord

logger = logging.getLogger(__name__)

# ODBC driver name for SQL Server connections
ODBC_DRIVER = "{ODBC Driver 18 for SQL Server}"

# Fetches the next batch of pending/failed replay rows, joined with the Messages
# table to retrieve the raw payload and correlation ID for each message.
# Uses READPAST to skip locked rows and reduce blocking between concurrent workers,
# and a parameterised TOP (?) for a configurable batch size.
FETCH_BATCH_SQL = """
WITH Batch AS (
    SELECT TOP (?) ReplayId, MessageId
    FROM monitoring.MessageReplayQueue WITH (READPAST)
    WHERE Status IN ('Failed', 'Pending')
    AND ReplayBatchId = ?
    ORDER BY ReplayId
)
SELECT b.ReplayId, m.Id AS MessageId, m.RawPayload, m.CorrelationId
FROM Batch b
JOIN monitoring.Message m ON m.Id = b.MessageId
ORDER BY b.ReplayId;
"""


class DatabaseClient:
    """Manages pyodbc connections to SQL Server for replay batch operations.

    Maintains a single persistent connection that is opened lazily on the first call
    and reused for all subsequent calls. If a database error occurs the stale connection
    is discarded so that the next call transparently reconnects (reconnect-on-failure).

    Supports two authentication modes:
    - **Password auth** (local dev): when ``sql_password`` is provided.
    - **Managed Identity auth** (production): when ``sql_password`` is ``None``, uses
      ``Authentication=ActiveDirectoryMsi``.
    """

    def __init__(
        self,
        sql_server: str,
        sql_database: str,
        sql_username: str | None,
        sql_password: str | None,
        sql_encrypt: str,
        sql_trust_server_certificate: str,
        managed_identity_client_id: str | None = None,
    ) -> None:
        # Validate that username and password are always provided together.
        username_provided = bool(sql_username)
        password_provided = bool(sql_password)
        if username_provided != password_provided:
            missing = "sql_password" if username_provided else "sql_username"
            provided = "sql_username" if username_provided else "sql_password"
            raise ValueError(
                f"{missing} must be provided when {provided} is set. "
                "Password authentication requires both a username and a password."
            )

        self._sql_server = sql_server
        self._sql_database = sql_database
        self._sql_username = sql_username
        self._sql_password = sql_password
        self._sql_encrypt = sql_encrypt
        self._sql_trust_server_certificate = sql_trust_server_certificate
        self._managed_identity_client_id = managed_identity_client_id
        # Persistent connection, opened lazily on first use.
        self._connection: pyodbc.Connection | None = None

    def fetch_batch(self, replay_batch_id: str, batch_size: int) -> List[ReplayRecord]:
        """Fetch the next batch of pending replay records up to ``batch_size`` rows.

        Executes the CTE query ordered by ReplayId, joining with the Messages table
        to retrieve the raw payload and correlation ID for each message.

        Args:
            replay_batch_id: The UUID identifying the replay batch.
            batch_size: Maximum number of rows to fetch in this call.

        Returns:
            A list of ReplayRecord objects, empty if no pending rows remain.

        Raises:
            pyodbc.Error: On any database-level failure.
        """
        connection = self._get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(FETCH_BATCH_SQL, (batch_size, replay_batch_id))
            rows = cursor.fetchall()
            return [
                ReplayRecord(
                    replay_id=row.ReplayId,
                    message_id=row.MessageId,
                    raw_payload=row.RawPayload,
                    correlation_id=row.CorrelationId,
                )
                for row in rows
            ]
        except Exception:
            logger.error("Failed to fetch replay batch — discarding connection", exc_info=True)
            self._close_connection()
            raise

    def update_statuses(self, replay_ids: List[int], status: str) -> None:
        """Update the status of the given replay records.

        Uses a single UPDATE with a dynamic WHERE IN clause for efficiency.
        Commits on success, rolls back and discards connection on error.

        Args:
            replay_ids: The ReplayId values to update.
            status: The new status string (e.g. 'Loaded', 'Failed').

        Raises:
            pyodbc.Error: On any database-level failure.
        """
        if not replay_ids:
            return

        connection = self._get_connection()
        placeholders = ", ".join("?" for _ in replay_ids)
        sql = f"""
UPDATE monitoring.MessageReplayQueue
SET Status = ?, ProcessedAt = SYSUTCDATETIME()
WHERE ReplayId IN ({placeholders});
"""  # nosec B608 — placeholders are parameterised ? markers, not user input
        params = [status] + list(replay_ids)

        try:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            connection.commit()
            logger.info("Updated %d replay record(s) to status '%s'", len(replay_ids), status)
        except Exception:
            try:
                connection.rollback()
                logger.debug("Transaction rolled back successfully")
            except Exception:
                logger.warning("Rollback failed", exc_info=True)
            logger.error("Failed to update statuses — discarding connection", exc_info=True)
            self._close_connection()
            raise

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Explicitly close the persistent connection, if open."""
        self._close_connection()

    def _get_connection(self) -> pyodbc.Connection:
        """Return the existing persistent connection, creating it if necessary."""
        if self._connection is None:
            logger.debug("No active connection — opening a new one")
            self._connection = self._connect()
        return self._connection

    def _close_connection(self) -> None:
        """Close and discard the cached connection."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                logger.debug("Error while closing connection (ignored)", exc_info=True)
            finally:
                self._connection = None

    def _connect(self) -> pyodbc.Connection:
        """Create a new pyodbc connection using the appropriate auth mode."""
        if self._sql_username and self._sql_password:
            return self._connect_with_password()
        return self._connect_with_managed_identity()

    def _build_base_connection_string(self) -> str:
        """Build the common ODBC connection string parts shared by both auth modes."""
        return (
            f"DRIVER={ODBC_DRIVER};"
            f"SERVER={self._sql_server};"
            f"DATABASE={self._sql_database};"
            f"Encrypt={self._sql_encrypt};"
            f"TrustServerCertificate={self._sql_trust_server_certificate}"
        )

    def _connect_with_password(self) -> pyodbc.Connection:
        """Connect using SQL username/password (local development)."""
        conn_str = f"{self._build_base_connection_string()};UID={self._sql_username};PWD={self._sql_password}"
        logger.debug("Connecting to SQL Server with password auth")
        return pyodbc.connect(conn_str, autocommit=False)

    def _connect_with_managed_identity(self) -> pyodbc.Connection:
        """Connect using Azure Managed Identity (production).

        Uses ``Authentication=ActiveDirectoryMsi`` in the ODBC connection string.
        For user-assigned identity, ``managed_identity_client_id`` is passed as ``UID``.
        """
        uid_segment = f"UID={self._managed_identity_client_id};" if self._managed_identity_client_id else ""
        conn_str = f"{self._build_base_connection_string()};{uid_segment}Authentication=ActiveDirectoryMsi"

        logger.debug("Connecting to SQL Server with Managed Identity auth")
        return pyodbc.connect(conn_str, autocommit=False)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "DatabaseClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self._close_connection()
        logger.debug("DatabaseClient context exited")


__all__ = ["DatabaseClient"]
