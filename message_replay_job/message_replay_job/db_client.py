import logging
import uuid
from types import TracebackType
from typing import List

import psycopg
from psycopg.rows import dict_row

from .entra_token import fetch_entra_access_token
from .replay_record import ReplayRecord
from .replay_status import ReplayStatus

logger = logging.getLogger(__name__)

# Fetches the next batch of pending/failed replay rows, joined with the message
# table to retrieve the raw payload and correlation ID for each message.
#
# FOR UPDATE SKIP LOCKED is the PostgreSQL equivalent of T-SQL's READPAST: it skips
# rows already locked by a concurrent worker instead of blocking on them. It must sit
# inside the CTE so that only the queue table is locked — locking is not permitted on
# the nullable side of an outer join, and there is no reason to lock the message rows.
#
# The locks are held until the surrounding transaction commits, which happens in
# update_statuses. That is what stops two workers claiming the same rows.
FETCH_BATCH_SQL = """
WITH batch AS (
    SELECT replay_id, message_id
    FROM monitoring.message_replay_queue
    WHERE status IN ('Failed', 'Pending')
    AND replay_batch_id = %s
    ORDER BY replay_id
    LIMIT %s
    FOR UPDATE SKIP LOCKED
)
SELECT b.replay_id, m.id AS message_id, m.raw_payload, m.correlation_id, m.session_id
FROM batch b
JOIN monitoring.message m ON m.id = b.message_id
ORDER BY b.replay_id;
"""


class DatabaseClient:
    """Manages psycopg connections to PostgreSQL for replay batch operations.

    Maintains a single persistent connection that is opened lazily on the first call
    and reused for all subsequent calls. If a database error occurs the stale connection
    is discarded so that the next call transparently reconnects (reconnect-on-failure).

    Supports two authentication modes:
    - **Password auth** (local dev): when ``pg_password`` is provided.
    - **Managed Identity auth** (production): when ``pg_password`` is ``None``, an Entra
      access token is acquired and passed as the connection password.

    Note that ``pg_user`` is required in *both* modes: with Entra auth it is the name
    of the database role mapped to the identity, not the identity's client ID.
    """

    def __init__(
        self,
        pg_host: str,
        pg_database: str,
        pg_user: str,
        pg_password: str | None,
        pg_port: int = 5432,
        pg_sslmode: str = "require",
        managed_identity_client_id: str | None = None,
    ) -> None:
        if not pg_user:
            raise ValueError(
                "pg_user must be provided. PostgreSQL requires a role name for both password "
                "and Entra (Managed Identity) authentication."
            )

        self._pg_host = pg_host
        self._pg_database = pg_database
        self._pg_user = pg_user
        self._pg_password = pg_password
        self._pg_port = pg_port
        self._pg_sslmode = pg_sslmode
        self._managed_identity_client_id = managed_identity_client_id
        # Persistent connection, opened lazily on first use.
        self._connection: psycopg.Connection | None = None

    def fetch_batch(self, replay_batch_id: str, batch_size: int) -> List[ReplayRecord]:
        """Fetch the next batch of pending replay records up to ``batch_size`` rows.

        Executes the CTE query ordered by replay_id, joining with the message table
        to retrieve the raw payload and correlation ID for each message.

        Args:
            replay_batch_id: The UUID identifying the replay batch.
            batch_size: Maximum number of rows to fetch in this call.

        Returns:
            A list of ReplayRecord objects, empty if no pending rows remain.

        Raises:
            ValueError: If ``replay_batch_id`` is not a valid UUID.
            psycopg.Error: On any database-level failure.
        """
        # replay_batch_id is a uuid column; adapt explicitly rather than relying on
        # server-side inference of an untyped text parameter.
        batch_uuid = uuid.UUID(replay_batch_id)

        connection = self._get_connection()
        try:
            cursor = connection.cursor(row_factory=dict_row)
            cursor.execute(FETCH_BATCH_SQL, (batch_uuid, batch_size))
            rows = cursor.fetchall()
            return [
                ReplayRecord(
                    replay_id=row["replay_id"],
                    message_id=row["message_id"],
                    raw_payload=row["raw_payload"],
                    correlation_id=row["correlation_id"],
                    session_id=row["session_id"],
                )
                for row in rows
            ]
        except Exception:
            logger.error("Failed to fetch replay batch — discarding connection", exc_info=True)
            self._close_connection()
            raise

    def update_statuses(self, replay_ids: List[int], status: ReplayStatus) -> None:
        """Update the status of the given replay records.

        Uses a single UPDATE with an ANY(%s) array predicate, which avoids building a
        variable-length placeholder list and keeps the statement text stable regardless
        of batch size (better for statement caching than the previous IN (?, ?, ...)).

        Commits on success, rolls back and discards connection on error. The commit also
        releases the row locks taken by ``fetch_batch``.

        Args:
            replay_ids: The replay_id values to update.
            status: The new status (e.g. ReplayStatus.LOADED, ReplayStatus.FAILED).

        Raises:
            psycopg.Error: On any database-level failure.
        """
        if not replay_ids:
            return

        connection = self._get_connection()
        sql = """
UPDATE monitoring.message_replay_queue
SET status = %s, processed_at = now()
WHERE replay_id = ANY(%s);
"""
        params: list[object] = [status, list(replay_ids)]

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

    def _get_connection(self) -> psycopg.Connection:
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

    def _connect(self) -> psycopg.Connection:
        """Create a new psycopg connection using the appropriate auth mode.

        The password is either the configured static password or a freshly acquired
        Entra access token; everything else about the connection is identical.
        """
        if self._pg_password:
            logger.debug("Connecting to PostgreSQL with password auth")
            password = self._pg_password
        else:
            logger.debug("Connecting to PostgreSQL with Managed Identity auth")
            password = fetch_entra_access_token(self._managed_identity_client_id)

        return psycopg.connect(
            host=self._pg_host,
            port=self._pg_port,
            dbname=self._pg_database,
            user=self._pg_user,
            password=password,
            sslmode=self._pg_sslmode,
            autocommit=False,
        )

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
