from __future__ import annotations

import logging
from typing import Any

from db_sender.db_client import DatabaseClient
from db_sender.handlers.base_handler import BaseDatabaseHandler
from db_sender.msh_extractor import MshInfo

logger = logging.getLogger(__name__)


class QueueMessageHandler(BaseDatabaseHandler):
    """Default handler: passes the raw message to dbo.prQueueMessage(@Message, @IsPriority)."""

    def handle_message(
        self,
        message_body: str,
        metadata: dict[str, Any],
        msh_info: MshInfo,
        db_client: DatabaseClient,
    ) -> None:
        is_priority = bool(self.config.default_is_priority)
        db_client.execute_stored_procedure(message_body, is_priority=is_priority)
