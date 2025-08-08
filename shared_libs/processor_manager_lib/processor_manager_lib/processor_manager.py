import logging
import signal
from types import FrameType
from typing import Optional

logger = logging.getLogger(__name__)


class ProcessorManager:

    def __init__(self) -> None:
        self._running = True
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

    def _shutdown_handler(self, signum: int, frame: Optional[FrameType]) -> None:
        logger.info("Shutting down the processor")
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def stop(self) -> None:
        logger.info("Manual processor stop requested")
        self._running = False


