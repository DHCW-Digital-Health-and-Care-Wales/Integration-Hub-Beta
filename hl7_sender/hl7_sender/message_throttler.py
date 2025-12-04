import logging
import time
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

SECONDS_PER_MINUTE = 60


class MessageThrottler:

    def __init__(self, messages_per_minute: Optional[int]):
        self.messages_per_minute = messages_per_minute
        self._timestamps: deque[float] = deque()

    def wait_if_needed(self) -> None:
        if self.messages_per_minute is None:
            return

        current_time = time.time()
        self._remove_expired_timestamps(current_time)

        if len(self._timestamps) >= self.messages_per_minute:
            oldest_timestamp = self._timestamps[0]
            wait_time = SECONDS_PER_MINUTE - (current_time - oldest_timestamp)
            if wait_time > 0:
                logger.info(
                    "Throttling: rate limit of %d messages/minute reached, waiting %.2f seconds",
                    self.messages_per_minute,
                    wait_time,
                )
                time.sleep(wait_time)
                self._remove_expired_timestamps(time.time())

    def record_message_sent(self) -> None:
        if self.messages_per_minute is not None:
            self._timestamps.append(time.time())

    def _remove_expired_timestamps(self, current_time: float) -> None:
        cutoff = current_time - SECONDS_PER_MINUTE
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

