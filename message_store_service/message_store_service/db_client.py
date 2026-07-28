import logging
from datetime import datetime, timezone
from types import TracebackType
from typing import List

import psycopg

from .entra_token import fetch_entra_access_token
from .message_record import MessageRecord

logger = logging.getLogger(__name__)


# SQL statement for batch-inserting message records into the monitoring.message table.
# Uses parameterised placeholders to prevent SQL injection.
INSERT_SQL = """
INSERT INTO monitoring.message (
    received_at,
    stored_at,
    correlation_id,
    source_system,
    processing_component,
    target_system,
    raw_payload,
    xml_payload,
    session_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


class DatabaseClient:
    """Manages psycopg connections to PostgreSQL and provides batch message inserts.

    Maintains a single persistent connection that is opened lazily on the first call
    to ``store_messages`` and reused for all subsequent calls.  If a database error
    occurs the stale connection is discarded so that the next call transparently
    reconnects (reconnect-on-failure strategy).

    Supports two authentication modes:
    - **Password auth** (local dev): when ``pg_password`` is provided, it is used
      directly as the connection password.
    - **Managed Identity auth** (production): when ``pg_password`` is ``None``, an
      Entra access token is acquired and passed as the connection *password*. This is
      how Azure Database for PostgreSQL Flexible Server accepts Entra credentials.
      A fresh token is fetched on every reconnect because tokens expire.

      For a **system-assigned** Managed Identity, omit ``managed_identity_client_id``.
      For a **user-assigned** Managed Identity, set it to the client ID of the identity.

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
        # Optional client ID for user-assigned Managed Identity.
        # When None, the system-assigned identity is used automatically.
        self._managed_identity_client_id = managed_identity_client_id
        # Persistent connection, opened lazily on first use.
        self._connection: psycopg.Connection | None = None

    def store_messages(self, messages: List[MessageRecord]) -> None:
        """Batch-insert a list of MessageRecord objects into monitoring.message.

        Wraps the operation in an atomic transaction (``autocommit=False``).  The
        underlying connection is reused across calls; if a database error occurs the
        connection is closed and discarded so that the next call transparently reconnects.

        If ``executemany`` raises, the transaction is rolled back so that a subsequent
        ``abandon_all`` on the Service Bus batch can safely re-queue without duplicates.

        Args:
            messages: The batch of message records to persist.

        Raises:
            psycopg.Error: On any database-level failure (connection, execution, etc.).
        """
        if not messages:
            logger.debug("No messages to store — skipping database insert")
            return

        connection = self._get_connection()
        stored_at = datetime.now(timezone.utc)

        try:
            cursor = connection.cursor()

            rows = [
                (
                    msg.received_at,
                    stored_at,
                    msg.correlation_id,
                    msg.source_system,
                    msg.processing_component,
                    msg.target_system,
                    msg.raw_payload,
                    msg.xml_payload,
                    msg.session_id,
                )
                for msg in messages
            ]

            cursor.executemany(INSERT_SQL, rows)
            connection.commit()
            logger.info("Successfully stored %d message(s) in database", len(messages))
        except Exception:
            try:
                connection.rollback()
                logger.debug("Transaction rolled back successfully")
            except Exception:
                logger.warning("Rollback failed", exc_info=True)
            logger.error("Database insert failed — discarding connection", exc_info=True)
            # Discard the stale connection so the next call reconnects cleanly.
            self._close_connection()
            raise

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Explicitly close the persistent connection, if open."""
        self._close_connection()

    def _get_connection(self) -> psycopg.Connection:
        """Return the existing persistent connection, creating it if necessary.

        Uses lazy initialisation: the connection is only established on the first
        call, then cached on ``self._connection`` for reuse across batches.
        If the cached connection has been closed externally (e.g. server-side
        timeout), a new one is opened transparently.
        """
        if self._connection is None:
            logger.debug("No active connection — opening a new one")
            self._connection = self._connect()
        return self._connection

    def _close_connection(self) -> None:
        """Close and discard the cached connection"""
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
