"""Apply an IterationSpec to a message's content for a given send index."""
from __future__ import annotations

from datetime import datetime

from ultra7.models import IterationSpec


def apply_iteration(content: str, spec: IterationSpec, iteration_index: int) -> str:
    """Return `content` with the highlighted substring recomputed for this send.

    `iteration_index` is 0-based (0 = first send). Falls back to leaving the
    original substring untouched if the range is out of bounds or unparsable.
    """
    if not (0 <= spec.start < spec.end <= len(content)):
        return content

    original = content[spec.start : spec.end]
    replacement = _compute_value(original, spec, iteration_index)
    return content[: spec.start] + replacement + content[spec.end :]


def _compute_value(original: str, spec: IterationSpec, iteration_index: int) -> str:
    if spec.mode == "increment":
        try:
            base = int(original)
        except ValueError:
            return original
        value = base + spec.step * iteration_index
        width = spec.pad_width or len(original)
        return str(value).zfill(width) if value >= 0 else str(value)

    if spec.mode == "list":
        if not spec.values:
            return original
        return spec.values[iteration_index % len(spec.values)]

    if spec.mode == "timestamp":
        return datetime.now().strftime(spec.timestamp_format)

    return original
