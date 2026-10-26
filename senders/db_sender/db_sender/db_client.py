from __future__ import annotations

import logging
import re
from typing import Any

import pyodbc

from db_sender.app_config import AppConfig

logger = logging.getLogger(__name__)

ODBC_DRIVER = "{ODBC Driver 18 for SQL Server}"

# Known transient SQLSTATE values
TRANSIENT_SQLSTATES = frozenset({
    "08001",  # Unable to connect to server
    "08003",  # Connection not open
    "08004",  # Server rejected connection
    "08007",  # Connection failure during transaction
    "08S01",  # Communication link failure
    "HYT00",  # Query timeout expired
    "HYT01",  # Connection timeout expired
    "40001",  # Serialization failure / deadlock victim
})

# Known transient SQL server native error codes
TRANSIENT_ERROR_CODES = frozenset({
    1205,   # Deadlock victim
    -2,     # Client timeout
    10054,  # Connection reset by peer
    10060,  # Connection timed out
    233,    # Connection initialization error
})


def sanitize_error_message(message: str) -> str:
    """Sanitize SQL Server diagnostic messages to prevent echoing clinical payloads or patient identifiers.

    In accordance with NHS Information Governance and Caldicott Principle 3,
    SQL Server diagnostic messages that echo parameter values (e.g. conversion error 245,
    duplicate key 2627/2601, string truncation 2628) must have echoed payload data redacted.
    """
    if not message:
        return ""

    sanitized = str(message)

    # Duplicate key value: "The duplicate key value is (9999999999, DOE)." -> "The duplicate key value is (***)."
    sanitized = re.sub(
        r"(The duplicate key value is\s*\()[^)]*(\))",
        r"\1***\2",
        sanitized,
        flags=re.IGNORECASE,
    )

    # Truncated value: "Truncated value: 'patient payload...'" -> "Truncated value: '***'"
    sanitized = re.sub(
        r"(Truncated value:\s*)'(?:''|[^'])*'",
        r"\1'***'",
        sanitized,
        flags=re.IGNORECASE,
    )

    # Conversion failed: "converting [the] [varchar] value '9999999999' to data type..." -> "...value '***' to..."
    sanitized = re.sub(
        r"(converting(?:\s+the)?(?:\s+\w+)?\s+value\s+)'(?:''|[^'])*'",
        r"\1'***'",
        sanitized,
        flags=re.IGNORECASE,
    )

    return sanitized


class DatabaseSenderError(Exception):
    """Base exception for database sender operations."""

    def __init__(self, message: str, sql_state: str = "UNKNOWN", error_code: int = 0) -> None:
        sanitized_message = sanitize_error_message(message)
        super().__init__(sanitized_message)
        self.sql_state = sql_state
        self.error_code = error_code
        self.error_message = sanitized_message


class TransientDatabaseError(DatabaseSenderError):
    """Temporary failure (e.g. network glitch, deadlock, timeout). Should be retried."""


class FatalDatabaseError(DatabaseSenderError):
    """Permanent failure (e.g. invalid stored procedure, schema mismatch, auth failure)."""


class DatabaseClient:
    """Manages pyodbc connection and stored procedure execution against Microsoft SQL Server."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._connection: pyodbc.Connection | None = None

    @staticmethod
    def _escape_credential(value: str) -> str:
        """Escape credential value for ODBC connection strings by brace-quoting and doubling closing braces."""
        return "{" + value.replace("}", "}}") + "}"

    def _build_connection_string(self) -> str:
        parts = [
            f"DRIVER={ODBC_DRIVER}",
            f"SERVER={self.config.db_server},{self.config.db_port}",
            f"DATABASE={self.config.db_name}",
            f"Encrypt={self.config.db_encrypt}",
            f"TrustServerCertificate={self.config.db_trust_server_certificate}",
        ]

        if self.config.db_username and self.config.db_password:
            # SQL Authentication (Local Dev / Test)
            parts.extend([
                f"UID={self._escape_credential(self.config.db_username)}",
                f"PWD={self._escape_credential(self.config.db_password)}",
            ])
        else:
            # Azure Active Directory / Managed Identity Authentication (Production Cloud)
            parts.append("Authentication=ActiveDirectoryMsi")
            if self.config.managed_identity_client_id:
                parts.append(f"UID={self.config.managed_identity_client_id}")

        return ";".join(parts) + ";"

    def _get_connection(self) -> pyodbc.Connection:
        if self._connection is None:
            conn_str = self._build_connection_string()
            logger.debug(
                "Establishing new connection to database: %s on %s",
                self.config.db_name,
                self.config.db_server,
            )
            self._connection = pyodbc.connect(
                conn_str,
                autocommit=False,
                timeout=self.config.db_connection_timeout,
            )
        return self._connection

    def close(self) -> None:
        """Close and discard the underlying connection if active."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                logger.debug("Error while closing connection (ignored)", exc_info=True)
            finally:
                self._connection = None

    def execute_stored_procedure(self, message_payload: str, is_priority: bool = False) -> None:
        """Execute the configured stored procedure with parameterised @Message and @IsPriority.

        Args:
            message_payload: The clinical message content (XML or ER7).
            is_priority: Bit flag for urgent/priority queuing (defaults to False / 0).

        Raises:
            TransientDatabaseError: If a transient network/timeout error occurred.
            FatalDatabaseError: If a non-recoverable SQL or configuration error occurred.
        """
        priority_val = 1 if is_priority else 0
        call_sql = f"{{CALL {self.config.db_stored_procedure} (?, ?)}}"

        try:
            conn = self._get_connection()
            conn.timeout = self.config.db_command_timeout
            with conn.cursor() as cursor:
                cursor.execute(call_sql, (message_payload, priority_val))
                conn.commit()
        except pyodbc.Error as err:
            self.close()
            sql_state, err_code, err_msg = self._parse_odbc_error(err)
            if self._is_transient(sql_state, err_code, err_msg):
                raise TransientDatabaseError(err_msg, sql_state=sql_state, error_code=err_code) from err
            raise FatalDatabaseError(err_msg, sql_state=sql_state, error_code=err_code) from err
        except Exception as err:
            self.close()
            sanitized = sanitize_error_message(str(err))
            raise TransientDatabaseError(sanitized, sql_state="UNKNOWN", error_code=0) from err

    @staticmethod
    def _parse_odbc_error(err: pyodbc.Error) -> tuple[str, int, str]:
        sql_state = "UNKNOWN"
        error_code = 0
        error_message = str(err)

        if err.args:
            # First arg in pyodbc error is usually SQLSTATE string
            if isinstance(err.args[0], str) and len(err.args[0]) == 5:
                sql_state = err.args[0]
            if len(err.args) > 1 and isinstance(err.args[1], str):
                error_message = err.args[1]

        # Look for [SQL Server] native error code in the string, e.g. [2812] or error code in args
        match = re.search(r"\[SQL Server\](?:\s*Error\s*(\d+)|\s*(\d+))", str(err))
        if match:
            found_code = match.group(1) or match.group(2)
            if found_code:
                try:
                    error_code = int(found_code)
                except ValueError:
                    pass

        return sql_state, error_code, sanitize_error_message(error_message)

    @staticmethod
    def _is_transient(sql_state: str, error_code: int, error_message: str) -> bool:
        if sql_state in TRANSIENT_SQLSTATES:
            return True
        if error_code in TRANSIENT_ERROR_CODES:
            return True
        msg_lower = error_message.lower()
        if "timeout" in msg_lower or "deadlock" in msg_lower or "communication link failure" in msg_lower:
            return True
        return False

    def __enter__(self) -> DatabaseClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
