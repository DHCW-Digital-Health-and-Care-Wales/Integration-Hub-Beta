import logging
from datetime import datetime, timezone
from types import TracebackType
from typing import List

import pyodbc

from .message_record import MessageRecord

logger = logging.getLogger(__name__)

# ODBC driver name for SQL Server connections
ODBC_DRIVER = "{ODBC Driver 18 for SQL Server}"


# SQL statement for batch-inserting message records into the monitoring.Message table.
# Uses parameterised placeholders to prevent SQL injection.
INSERT_SQL = """
INSERT INTO monitoring.Message (
    ReceivedAt,
    StoredAt,
    CorrelationId,
    SourceSystem,
    ProcessingComponent,
    TargetSystem,
    RawPayload,
    XmlPayload
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


class DatabaseClient:
    """Manages pyodbc connections to SQL Server and provides batch message inserts.

    Maintains a single persistent connection that is opened lazily on the first call
    to ``store_messages`` and reused for all subsequent calls.  If a database error
    occurs the stale connection is discarded so that the next call transparently
    reconnects (reconnect-on-failure strategy).

    Supports two authentication modes:
    - **Password auth** (local dev): when ``sql_password`` is provided, connects with
      username/password via the ODBC connection string.
    - **Managed Identity auth** (production): when ``sql_password`` is ``None``, uses
      ``Authentication=ActiveDirectoryMsi`` in the ODBC connection string so the
      driver authenticates directly via Azure Managed Identity

      For a **system-assigned** Managed Identity, omit ``managed_identity_client_id``.
      For a **user-assigned** Managed Identity, set ``managed_identity_client_id`` to
      the client ID of the identity; it is passed as ``UID`` so the driver targets
      the correct identity.
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
        self._sql_server = sql_server
        self._sql_database = sql_database
        self._sql_username = sql_username
        self._sql_password = sql_password
        self._sql_encrypt = sql_encrypt
        self._sql_trust_server_certificate = sql_trust_server_certificate
        # Optional client ID for user-assigned Managed Identity.
        # When None, the system-assigned identity is used automatically.
        self._managed_identity_client_id = managed_identity_client_id
        # Persistent connection, opened lazily on first use.
        self._connection: pyodbc.Connection | None = None

    def store_messages(self, messages: List[MessageRecord]) -> None:
        """Batch-insert a list of MessageRecord objects into monitoring.Message.

        Uses ``fast_executemany`` for performance and wraps the operation in an
        atomic transaction (``autocommit=False``).  The underlying connection is
        reused across calls; if a database error occurs the connection is closed and
        discarded so that the next call transparently reconnects.

        If ``executemany`` raises, the transaction is rolled back so that a subsequent
        ``abandon_all`` on the Service Bus batch can safely re-queue without duplicates.

        Args:
            messages: The batch of message records to persist.

        Raises:
            pyodbc.Error: On any database-level failure (connection, execution, etc.).
        """
        if not messages:
            logger.debug("No messages to store — skipping database insert")
            return

        connection = self._get_connection()
        stored_at = datetime.now(timezone.utc)

        try:
            cursor = connection.cursor()
            # Enable fast_executemany for batch performance
            cursor.fast_executemany = True

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
                )
                for msg in messages
            ]

            cursor.executemany(INSERT_SQL, rows)
            connection.commit()
            logger.info("Successfully stored %d message(s) in database", len(messages))
        except Exception:
            connection.rollback()
            logger.error("Database insert failed — transaction rolled back; discarding connection", exc_info=True)
            # Discard the stale connection so the next call reconnects cleanly.
            self._close_connection()
            raise

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Explicitly close the persistent connection, if open."""
        self._close_connection()

    def _get_connection(self) -> pyodbc.Connection:
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

    def _connect(self) -> pyodbc.Connection:
        """Create a new pyodbc connection using the appropriate auth mode."""
        if self._sql_password:
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
        conn_str = (
            f"{self._build_base_connection_string()};"
            f"UID={self._sql_username};"
            f"PWD={self._sql_password}"
        )
        logger.debug("Connecting to SQL Server with password auth")
        return pyodbc.connect(conn_str, autocommit=False)

    def _connect_with_managed_identity(self) -> pyodbc.Connection:
        """Connect using Azure Managed Identity (production).

        Uses ``Authentication=ActiveDirectoryMsi`` in the ODBC connection string,
        allowing the ODBC driver to handle Managed Identity authentication directly.

        - System-assigned identity: ``managed_identity_client_id`` is ``None``, so
          ``UID`` is omitted and the driver picks up the single assigned identity.
        - User-assigned identity: ``managed_identity_client_id`` is set to the client
          ID of the target identity, passed as ``UID`` for explicit selection.
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

