from dataclasses import dataclass


@dataclass(frozen=True)
class ReplayRecord:
    """Represents one row from the replay batch query."""

    replay_id: int
    message_id: int
    raw_payload: str
    correlation_id: str
    session_id: str


__all__ = ["ReplayRecord"]
