from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingResult:
    success: bool
    error_reason: str | None = None
    retry: bool | None = None

    @staticmethod
    def successful() -> ProcessingResult:
        return ProcessingResult(success=True)

    @staticmethod
    def failed(error_reason: str | None = None, retry: bool | None = False) -> ProcessingResult:
        return ProcessingResult(success=False, error_reason=error_reason, retry=retry)
