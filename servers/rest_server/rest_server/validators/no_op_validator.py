"""No-op validator - skips schema validation entirely.

Use only with an explicit, documented justification: this removes the schema trust boundary and
relies solely on network controls and well-formedness/size checks upstream.
"""
from __future__ import annotations


class NoOpValidator:
    def validate(self, payload_xml: str, structure_id: str | None) -> None:
        return None
