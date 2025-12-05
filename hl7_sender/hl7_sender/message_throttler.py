import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

SECONDS_PER_MINUTE = 60


class MessageThrottler:

    def __init__(self, max_messages_per_minute: Optional[int]):
        self._max_messages_per_minute = max_messages_per_minute
        self._last_message_time: Optional[float] = None

    def wait_if_needed(self) -> None:
        if self._max_messages_per_minute is None or self._max_messages_per_minute <= 0:
            return

        now = time.monotonic()

        if self._last_message_time is not None:
            min_interval = SECONDS_PER_MINUTE / self._max_messages_per_minute
            elapsed = now - self._last_message_time
            wait_time = min_interval - elapsed

            if wait_time > 0:
                logger.info(
                    "Throttling: waiting %.2f seconds to maintain %d messages/minute rate",
                    wait_time,
                    self._max_messages_per_minute,
                )
                time.sleep(wait_time)
                now = time.monotonic()

        self._last_message_time = now
