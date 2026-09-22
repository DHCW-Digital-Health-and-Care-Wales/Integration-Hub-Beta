"""Core Reference Transformer plugin — RISP -> MPI WRDS field translation preview.

CoreReferenceTransformer.__init__ reads config.ini and connects to Azure Service Bus, and its
apply_core_reference_mapping() dependency (WRDSService) normally calls a live WRDS SOAP endpoint.
Neither is available locally, so this plugin:
  1. Calls apply_core_reference_mapping() directly (the standalone mapping function — no
     CoreReferenceTransformer instantiation needed, same pattern as the Chemo/PIMS plugins).
  2. Builds a WRDSService pointed at a small in-memory fixture file (a handful of demo FromCode ->
     ToCode rows matching the six in-scope PID fields) instead of a live endpoint, so no network
     call is ever made.

This means the ToCode values shown are **demo data only**, not real WRDS lookups.
"""
from __future__ import annotations

import atexit
import os
import tempfile

from .base import ServicePlugin

# Only these six PID fields may ever be translated (see FIELD_TYPE_MAP in pid_reference_mapper.py).
# The FromCode values below match the field values used in the sample messages so every field
# resolves to a ToCode in the demo fixture (nothing is left blank because of a missing lookup row).
_DEMO_ROWS: list[tuple[str, str, str]] = [
    # (FromCode, Type, ToCode)
    ("1", "Sex", "M"),
    ("2", "Sex", "F"),
    ("Mr.", "Title", "Mr"),
    ("Mrs.", "Title", "Mrs"),
    ("EN", "Language", "eng"),
    ("CY", "Language", "cym"),
    ("11", "Marital Status", "S"),
    ("22", "Religion", "REL22"),
    ("33", "Ethnicity", "ETH33"),
]

_NRDS_NS = "http://www.wales.nhs.uk/nrds"
_MES_NS = "http://www.wales.nhs.uk/namespaces/MessageRelease2"


def _build_demo_fixture_xml() -> str:
    """Build a raw SOAP GetResultSetResponse body from _DEMO_ROWS (same shape WRDSService parses)."""
    rows_xml = "".join(
        f"""
      <Row>
        <AttributeValuePair>
          <Attribute><Id></Id><Name>FromCode</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value>{from_code}</Value>
        </AttributeValuePair>
        <AttributeValuePair>
          <Attribute><Id></Id><Name>Type</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value>{reference_type}</Value>
        </AttributeValuePair>
        <AttributeValuePair>
          <Attribute><Id></Id><Name>ToCode</Name><Namespace>{_NRDS_NS}</Namespace></Attribute>
          <Value>{to_code}</Value>
        </AttributeValuePair>
      </Row>"""
        for from_code, reference_type, to_code in _DEMO_ROWS
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetResultSetResponse xmlns="{_MES_NS}">{rows_xml}
    </GetResultSetResponse>
  </soap:Body>
</soap:Envelope>"""


def _demo_fixture_path() -> str:
    """Write the demo fixture to a temp file once per process and return its path."""
    fd, path = tempfile.mkstemp(prefix="wrds_demo_fixture_", suffix=".xml")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(_build_demo_fixture_xml())
    atexit.register(lambda: os.path.exists(path) and os.remove(path))
    return path


# Same field layout as tests/messages.py in hl7_core_reference_transformer (kept in sync manually —
# that module isn't importable here without pulling in test-only code).
_A28_ALL_FIELDS = """\
MSH|^~\\&|349|349|100|100|20250624162400||ADT^A28|123456789|P|2.5|||NE|NE
PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^^^Mr.||20000101000000|1|||||||EN^English|11^Single|22^SomeReligion|||||33^SomeEthnicity"""

_A31_NO_CODED_FIELDS = """\
MSH|^~\\&|349|349|100|100|20250624162400||ADT^A31|123456789|P|2.5|||NE|NE
PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST||20000101000000"""

_A04_OUT_OF_SCOPE = """\
MSH|^~\\&|349|349|100|100|20250624162400||ADT^A04|123456789|P|2.5|||NE|NE
PID|1||1000000001^^^^NH||TEST^TEST|||1"""


class CoreReferencePlugin(ServicePlugin):
    tab_label = "Core Reference Transformer"
    description = (
        "RISP ADT (A28/A31/A40) → same message with PID Sex/Title/Language/Marital Status/"
        "Religion/Ethnicity translated via WRDS  ⚠ demo fixture data, not a live WRDS lookup"
    )
    input_label = "Inbound HL7v2 ER7  (RISP)"
    output_label = "Transformed HL7v2 ER7 (PID fields translated)"
    button_label = "▶  Transform"
    samples = {
        "A28 (all 6 fields populated)": _A28_ALL_FIELDS,
        "A31 (no coded fields)": _A31_NO_CODED_FIELDS,
        "A04 (out of scope — passes through)": _A04_OUT_OF_SCOPE,
    }

    def __init__(self) -> None:
        self._fixture_path: str | None = None

    def run(self, input_text: str) -> tuple[str, str]:
        from hl7apy.parser import parse_message
        from wrds_service import WRDSService

        from hl7_core_reference_transformer.mappers.pid_reference_mapper import (
            apply_core_reference_mapping,
        )

        if self._fixture_path is None:
            self._fixture_path = _demo_fixture_path()

        er7 = input_text.strip().replace("\n", "\r")
        msg = parse_message(er7, find_groups=False)

        trigger_event = msg.msh.msh_9.msg_2.value if msg.msh.msh_9.msg_2.value else ""
        if trigger_event not in {"A28", "A31", "A40"}:
            er7_out = er7.replace("\r", "\n")
            return er7_out, f"✓  {trigger_event or '(unknown)'} is out of scope — passed through unchanged"

        wrds_service = WRDSService(endpoint_url="https://demo.invalid/wrdssoapservice", fixture_file_path=self._fixture_path)
        result = apply_core_reference_mapping(msg, wrds_service, "FioranoCodeTranslation")

        output = result.to_er7().replace("\r", "\n")
        return output, "✓  PID reference fields translated (demo fixture data)"
