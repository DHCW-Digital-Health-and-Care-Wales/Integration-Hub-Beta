"""FHIR JSON codec - generic wire-format adapter for "parse X -> FHIR Bundle" transformers.

The inbound parse step is pluggable (different FHIR-producing transformers
may receive different source formats - WPAS XML today, perhaps a JSON
source system in future) - only the *output* side (FHIR Bundle -> JSON) is
fixed by this codec, since that's shared by every FHIR-producing transformer.

Note: transformer_base_lib does not depend on fhir.resources directly (to
keep it a lightweight dependency for non-FHIR transformers) - the output
type only needs to duck-type a pydantic-style `model_dump_json()` method,
which fhir.resources.R4B models (e.g. Bundle) satisfy.
"""
from __future__ import annotations

from typing import Callable, Protocol, TypeVar

from .base_codec import MessageCodec

TParsed = TypeVar("TParsed")


class _JsonSerialisable(Protocol):
    def model_dump_json(self) -> str: ...


TSerialisable = TypeVar("TSerialisable", bound=_JsonSerialisable)


class FhirJsonCodec(MessageCodec[TParsed, TSerialisable]):
    """Parses an inbound payload via an injected parse function; serialises FHIR Bundles to JSON."""

    def __init__(self, parse_fn: Callable[[str], TParsed]) -> None:
        self._parse_fn = parse_fn

    def parse(self, message_body: str) -> TParsed:
        return self._parse_fn(message_body)

    def serialise(self, transformed_message: TSerialisable) -> str:
        return transformed_message.model_dump_json()
