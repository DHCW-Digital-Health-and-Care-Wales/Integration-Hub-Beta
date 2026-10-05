"""Composite-key handling.

This is the single place that turns caller input (positional or named parts) into the canonical key:
a tuple of normalised parts in the table's `key_columns` order. Stores, caches and (later) Cosmos ids
only ever see canonical keys, so normalisation can't drift between load and lookup.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from lookup_service.errors import InvalidKeyError
from lookup_service.models import KeyPartRule, TableDefinition


def normalise_part(value: str, rule: KeyPartRule) -> str:
    if rule.trim:
        value = value.strip()
    if rule.case == "upper":
        return value.upper()
    if rule.case == "lower":
        return value.lower()
    return value


def canonical_key(
    definition: TableDefinition,
    positional: Sequence[str] = (),
    named: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Build the canonical key from exactly one of positional or named parts.

    Raises InvalidKeyError for a missing key, mixed styles, wrong arity, unknown/missing part names,
    or a part that is empty after normalisation.
    """
    named = named or {}
    if positional and named:
        raise InvalidKeyError("Supply the key either positionally (k=) or by name (key.<part>=), not both",
                              definition.name)
    if named:
        raw_parts = _parts_from_named(definition, named)
    elif positional:
        raw_parts = _parts_from_positional(definition, positional)
    else:
        raise InvalidKeyError(f"No key supplied; expected parts {_describe(definition)}", definition.name)

    parts = []
    for column, raw in zip(definition.key_columns, raw_parts, strict=True):
        part = normalise_part(raw, definition.rule_for(column))
        if not part:
            raise InvalidKeyError(f"Key part {column!r} is empty", definition.name)
        parts.append(part)
    return tuple(parts)


def _parts_from_positional(definition: TableDefinition, positional: Sequence[str]) -> list[str]:
    expected = len(definition.key_columns)
    if len(positional) != expected:
        raise InvalidKeyError(
            f"Expected {expected} key part(s) {_describe(definition)}, got {len(positional)}", definition.name
        )
    return list(positional)


def _parts_from_named(definition: TableDefinition, named: Mapping[str, str]) -> list[str]:
    unknown = sorted(set(named) - set(definition.key_columns))
    if unknown:
        raise InvalidKeyError(f"Unknown key part(s) {unknown}; expected {_describe(definition)}", definition.name)
    missing = [column for column in definition.key_columns if column not in named]
    if missing:
        raise InvalidKeyError(f"Missing key part(s) {missing}; expected {_describe(definition)}", definition.name)
    return [named[column] for column in definition.key_columns]


def _describe(definition: TableDefinition) -> str:
    return "(" + ", ".join(definition.key_columns) + ")"
