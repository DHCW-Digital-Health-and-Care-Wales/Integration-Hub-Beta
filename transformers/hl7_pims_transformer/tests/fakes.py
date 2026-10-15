"""Test doubles for the PIMS transformer tests."""

from __future__ import annotations

from typing import Dict, Tuple

from hl7_pims_transformer.clients.reference_data_client import (
    ReferenceDataLookupError,
    ReferenceDataset,
)


class IdentityLookupClient:
    """A ``ReferenceDataLookupClient`` stand-in that echoes the source code back.

    Lets mapper/transformer tests exercise the enrichment path deterministically without any HTTP
    traffic: looking up a gender of ``F`` simply yields ``F``.
    """

    def lookup(self, dataset: ReferenceDataset, source_code: str) -> str:
        return source_code.strip()


class StubLookupClient:
    """A ``ReferenceDataLookupClient`` stand-in returning preconfigured codes per (dataset, source).

    Unknown (dataset, source) pairs raise :class:`ReferenceDataLookupError`, mirroring the real
    client's "no mapping / invalid" behaviour.
    """

    def __init__(self, mappings: Dict[Tuple[ReferenceDataset, str], str]) -> None:
        self._mappings = mappings

    def lookup(self, dataset: ReferenceDataset, source_code: str) -> str:
        key = (dataset, source_code.strip())
        if key not in self._mappings:
            raise ReferenceDataLookupError(
                f"No stub mapping for dataset '{dataset.path}' (source '{source_code}')."
            )
        return self._mappings[key]
