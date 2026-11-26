"""Apply one or more IterationSpecs to a message's content for a given send index."""
from __future__ import annotations

import random
from datetime import datetime

from ultra7.models import IterationSpec
from ultra7.nhs_number import generate_nhs_number


def apply_iteration(
    content: str,
    spec: IterationSpec,
    iteration_index: int,
    rng: random.Random | None = None,
) -> str:
    """Return `content` with the highlighted substring recomputed for this send.

    `iteration_index` is 0-based (0 = first send). Falls back to leaving the
    original substring untouched if the range is out of bounds or unparsable.
    """
    if not (0 <= spec.start < spec.end <= len(content)):
        return content

    original = content[spec.start : spec.end]
    replacement = _compute_value(original, spec, iteration_index, rng=rng)
    return content[: spec.start] + replacement + content[spec.end :]


def apply_iterations(
    content: str,
    specs: list[IterationSpec],
    iteration_index: int,
    rng: random.Random | None = None,
) -> str:
    """Apply multiple non-overlapping IterationSpecs safely (from right to left)."""
    if not specs:
        return content
    result = content
    # Sort descending by start offset so replacing a later span doesn't shift earlier offsets.
    for spec in sorted(specs, key=lambda s: s.start, reverse=True):
        result = apply_iteration(result, spec, iteration_index, rng=rng)
    return result


def _compute_value(
    original: str,
    spec: IterationSpec,
    iteration_index: int,
    rng: random.Random | None = None,
) -> str:
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

    if spec.mode == "nhs_number":
        return generate_nhs_number(rng=rng, spaced=" " in original)

    return original
