import logging
from typing import Any, Optional

from hl7apy.core import Field, Message

logger = logging.getLogger(__name__)


class DeathDateFilterResult:

    def __init__(self, should_forward: bool, reason: str, pid_29_ts1_value: Optional[str] = None,
                 pid_30_value: Optional[str] = None):
        self.should_forward = should_forward
        self.reason = reason
        self.pid_29_ts1_value = pid_29_ts1_value
        self.pid_30_value = pid_30_value


class DeathDateFilter:

    def __init__(self) -> None:
        self.accepted_message_types = {"ADT^A28", "ADT^A31"}

    def should_forward_message(self, hl7_message: Message) -> DeathDateFilterResult:
        try:
            # Check if message type is supported
            message_type = hl7_message.msh.msh_9.to_er7()
            if not self._is_supported_message_type(message_type):
                return DeathDateFilterResult(
                    should_forward=False,
                    reason=f"Unsupported message type: {message_type}"
                )

            # Extract PID segment
            pid_segment = getattr(hl7_message, "pid", None)
            if pid_segment is None:
                return DeathDateFilterResult(
                    should_forward=False,
                    reason="No PID segment found in message"
                )

            # Check PID.29.TS.1 (Date/Time of Death timestamp)
            pid_29_ts1_value = self._extract_pid_29_ts1_value(pid_segment)
            pid_29_ts1_populated = self._is_field_populated(pid_29_ts1_value)

            # Check PID.30 (Death Indicator)
            pid_30_field = getattr(pid_segment, "pid_30", None)
            pid_30_value = self._extract_field_value(pid_30_field)
            pid_30_populated = self._is_field_populated(pid_30_value)

            logger.debug(f"PID.29 value: '{pid_29_ts1_value}', populated: {pid_29_ts1_populated}")
            logger.debug(f"PID.30 value: '{pid_30_value}', populated: {pid_30_populated}")

            # Apply filtering logic: forward if either field is populated
            if pid_29_ts1_populated or pid_30_populated:
                reason_parts = []
                if pid_29_ts1_populated:
                    reason_parts.append("PID.29.TS.1 (Date/Time of Death timestamp) populated")
                if pid_30_populated:
                    reason_parts.append("PID.30 (Death Indicator) populated")

                return DeathDateFilterResult(
                    should_forward=True,
                    reason=f"Message accepted: {' and '.join(reason_parts)}",
                    pid_29_ts1_value=pid_29_ts1_value,
                    pid_30_value=pid_30_value
                )
            else:
                return DeathDateFilterResult(
                    should_forward=False,
                    reason="Message dropped: Neither PID.29.TS.1 nor PID.30 are populated",
                    pid_29_ts1_value=pid_29_ts1_value,
                    pid_30_value=pid_30_value
                )

        except Exception as e:
            logger.error(f"Error during death date filtering: {e}")
            return DeathDateFilterResult(
                should_forward=False,
                reason=f"Filter error: {str(e)}"
            )

    def _is_supported_message_type(self, message_type: str) -> bool:
        return message_type in self.accepted_message_types

    def _extract_pid_29_ts1_value(self, pid_segment: Any) -> Optional[str]:
        pid_29_field = getattr(pid_segment, "pid_29", None)
        if pid_29_field is None:
            return None

        if isinstance(pid_29_field, Field):
            try:
                if hasattr(pid_29_field, 'ts_1') and pid_29_field.ts_1:
                    return self._extract_field_value(pid_29_field.ts_1)
                else:
                    return None
            except Exception:
                return None
        else:
            return None

    def _extract_field_value(self, field: Any) -> Optional[str]:
        if field is None:
            return None

        if hasattr(field, 'value'):
            return field.value

        if isinstance(field, str):
            return field

        try:
            return str(field)
        except Exception:
            return None

    def _is_field_populated(self, field_value: Optional[str]) -> bool:
        return field_value is not None and field_value.strip() != ""
