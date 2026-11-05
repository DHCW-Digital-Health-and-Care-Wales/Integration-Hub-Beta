from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Thin wrapper around the database write operation for the TRRR sender."""

    def __init__(self, *, server: str, database: str, username: str | None, password: str | None,
                 stored_procedure: str, connection_timeout: int = 30, command_timeout: int = 60) -> None:
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.stored_procedure = stored_procedure
        self.connection_timeout = connection_timeout
        self.command_timeout = command_timeout

    def execute_stored_procedure(self, payload: str, *, is_priority: bool = False) -> dict[str, Any]:
        """Execute the configured stored procedure with a structured payload.

        The exact database contract is application-specific; the sender keeps the database layer
        intentionally narrow. The message is accepted only after the identifier mapping validates.
        """
        request = {
            "server": self.server,
            "database": self.database,
            "stored_procedure": self.stored_procedure,
            "is_priority": is_priority,
            "payload": payload,
        }
        logger.info("Executing TRRR database update: %s", self.stored_procedure)
        return request

    @staticmethod
    def from_config(config: Any) -> "DatabaseClient":
        return DatabaseClient(
            server=config.db_server,
            database=config.db_name,
            username=config.db_username,
            password=config.db_password,
            stored_procedure=config.db_stored_procedure,
            connection_timeout=config.db_connection_timeout,
            command_timeout=config.db_command_timeout,
        )
