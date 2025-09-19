import logging
from typing import Any, Optional

from event_logger_lib.event_logger import EventLogger
from hl7apy.mllp import MLLPServer

from hl7_server.size_limited_mllp_request_handler import SizeLimitedMLLPRequestHandler

logger = logging.getLogger(__name__)


class SizeLimitedMLLPServer(MLLPServer):

    def __init__(
        self,
        host: str,
        port: int,
        handlers: dict[str, Any],
        max_message_size_bytes: int = 1048576,  # Default 1MB
        event_logger: Optional[EventLogger] = None,
        timeout: int = 10
    ) -> None:
        if max_message_size_bytes <= 0:
            logger.warning(
                f"Invalid message size limit {max_message_size_bytes}, using default 1MB"
            )
            max_message_size_bytes = 1048576

        # Log warning for very large size limits (>100MB)
        if max_message_size_bytes > 104857600:
            logger.warning(
                f"Very large message size limit configured: {max_message_size_bytes} bytes. "
                f"Consider if this is appropriate for your use case."
            )

        self.max_message_size_bytes = max_message_size_bytes
        self.event_logger = event_logger

        # Initialize parent class with custom request handler
        super().__init__(
            host=host,
            port=port,
            handlers=handlers,
            timeout=timeout,
            request_handler_class=SizeLimitedMLLPRequestHandler
        )

        logger.info(
            f"MLLP Server initialized on {host}:{port} with message size limit: "
            f"{max_message_size_bytes} bytes ({max_message_size_bytes / 1024 / 1024:.1f}MB)"
        )

    def get_max_message_size_mb(self) -> float:
        return round(self.max_message_size_bytes / 1024 / 1024, 1)
