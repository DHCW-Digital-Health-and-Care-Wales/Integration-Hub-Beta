from __future__ import annotations

from db_sender.app_config import AppConfig
from db_sender.handlers.base_handler import BaseDatabaseHandler
from db_sender.handlers.queue_idupd_handler import QueueIdUpdateHandler
from db_sender.handlers.queue_message_handler import QueueMessageHandler

__all__ = [
    "BaseDatabaseHandler",
    "QueueIdUpdateHandler",
    "QueueMessageHandler",
    "create_handler",
]


def create_handler(config: AppConfig) -> BaseDatabaseHandler:
    """Factory creating the appropriate database handler based on DB_PROCEDURE_TYPE."""
    proc_type = config.db_procedure_type.strip().lower()
    if proc_type == "queue_id_update":
        return QueueIdUpdateHandler(config)
    return QueueMessageHandler(config)
