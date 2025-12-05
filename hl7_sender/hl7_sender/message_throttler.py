import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

SECONDS_PER_MINUTE = 60


class MessageThrottler:

    def __init__(self, max_messages_per_minute: Optional[int]):
        self._max_messages_per_minute = max_messages_per_minute
        self._interval = (
            SECONDS_PER_MINUTE / max_messages_per_minute
            if max_messages_per_minute and max_messages_per_minute > 0
            else None
        )
        self._last_message_time: Optional[float] = None

    def wait_if_needed(self) -> None:
        if self._interval is None:
            return

        now = time.monotonic()
        target_time = now

        if self._last_message_time is not None:
            target_time = self._last_message_time + self._interval
            wait_time = target_time - now

            if wait_time > 0:
                logger.info(
                    "Throttling: waiting %.2f seconds to maintain %d messages/minute rate",
                    wait_time,
                    self._max_messages_per_minute,
                )
                time.sleep(wait_time)
            else:
                target_time = now

        self._last_message_time = target_time
