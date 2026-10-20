from __future__ import annotations

from collections.abc import Iterable

from lookup_service.mapping.model import Transform


def apply_transforms(value: str, transforms: Iterable[Transform]) -> str:
    for transform in transforms:
        if transform == "trim":
            value = value.strip()
        elif transform == "upper":
            value = value.upper()
        elif transform == "lower":
            value = value.lower()
        else:  # pragma: no cover - guarded by the Transform literal type
            raise ValueError(f"Unknown transform {transform!r}")
    return value
