from enum import Enum


class ReplayStatus(str, Enum):
    """Status values for rows in the MessageReplayQueue table."""

    PENDING = "Pending"
    FAILED = "Failed"
    LOADED = "Loaded"


__all__ = ["ReplayStatus"]
