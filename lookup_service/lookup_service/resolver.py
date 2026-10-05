from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from lookup_service.errors import InvalidKeyError, KeyNotFoundError
from lookup_service.keys import canonical_key
from lookup_service.models import LookupResult
from lookup_service.store.base import TableStore

NAMED_KEY_PREFIX = "key."


def named_key_params(table: str, params: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Collect `key.<part>=value` query/form parameters, rejecting a part supplied more than once."""
    named: dict[str, str] = {}
    for name, value in params:
        if not name.startswith(NAMED_KEY_PREFIX):
            continue
        part = name[len(NAMED_KEY_PREFIX):]
        if part in named:
            raise InvalidKeyError(f"Key part {part!r} supplied more than once", table)
        named[part] = value
    return named


async def resolve_lookup(
    store: TableStore,
    table: str,
    positional: Sequence[str] = (),
    named: Mapping[str, str] | None = None,
) -> LookupResult:
    definition = await store.get_definition(table)
    key = canonical_key(definition, positional, named)
    row = await store.get_row(table, key)
    if row is None:
        # Deliberately no key values in the message: it can end up in caller logs.
        raise KeyNotFoundError(f"No row for the supplied key in table {table!r}", table)
    return LookupResult(
        table=table,
        key=list(key),
        value=row.values[definition.default_value_column],
        values=dict(row.values),
        source=store.source,
        cached=True,
    )
