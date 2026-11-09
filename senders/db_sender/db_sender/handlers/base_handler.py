from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from db_sender.app_config import AppConfig
from db_sender.db_client import DatabaseClient
from db_sender.msh_extractor import MshInfo


class BaseDatabaseHandler(ABC):
    """Abstract base handler for database sender execution strategies."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @abstractmethod
    def handle_message(
        self,
        message_body: str,
        metadata: dict[str, Any],
        msh_info: MshInfo,
        db_client: DatabaseClient,
    ) -> None:
        """Process an inbound message and execute the appropriate database call."""
        pass
