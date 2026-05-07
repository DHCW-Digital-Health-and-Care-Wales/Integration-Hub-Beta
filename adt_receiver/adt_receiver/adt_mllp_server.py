import logging
from typing import Any, Optional

from event_logger_lib.event_logger import EventLogger
from hl7apy.mllp import MLLPServer

from adt_receiver.adt_mllp_request_handler import AdtMllpRequestHandler

logger = logging.getLogger(__name__)


class AdtMllpServer(MLLPServer):

    def __init__(
        self,
        host: str,
        port: int,
        handlers: dict[str, Any],
        max_message_size_bytes: int,
        event_logger: Optional[EventLogger] = None,
        timeout: int = 10,
    ) -> None:
        self.max_message_size_bytes = max_message_size_bytes
        self.event_logger = event_logger

        super().__init__(
            host=host,
            port=port,
            handlers=handlers,
            timeout=timeout,
            request_handler_class=AdtMllpRequestHandler,
        )

        logger.info(
            "ADT MLLP Server initialized on %s:%d with message size limit: %d bytes (%.1fMB)",
            host,
            port,
            max_message_size_bytes,
            max_message_size_bytes / 1024 / 1024,
        )
