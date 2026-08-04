"""PROMS Transformer plugin.

transform_proms_xml_to_fhir_bundle() is a standalone function — no class init needed.
"""
from __future__ import annotations

import json

from .base import ServicePlugin

_PROMS_OPI = """\
<?xml version="1.0" encoding="UTF-8"?>
<OPI>
  <SYSTEM_ID>108</SYSTEM_ID>
  <DHA_CODE>7A3</DHA_CODE>
  <UNIQUE_ID>EPISODE-00123</UNIQUE_ID>
  <NHS_NUMBER>9434765919</NHS_NUMBER>
  <NHS_CERTIFICATION>01</NHS_CERTIFICATION>
  <UNIT_NUMBER>SB0099887</UNIT_NUMBER>
  <SURNAME>Bevan</SURNAME>
  <FORENAME>Aneurin</FORENAME>
  <SEX>1</SEX>
  <BIRTHDATE>1897-11-15</BIRTHDATE>
  <POSTCODE>SA1 1AA</POSTCODE>
  <SPEC>110</SPEC>
  <SPEC_NAME>Trauma and Orthopaedics</SPEC_NAME>
  <CONS_NAME>Dr James Chess</CONS_NAME>
  <CONS_GMC>1234567</CONS_GMC>
  <UPI_EVENT>OP01</UPI_EVENT>
  <UPI_EVENT_DESC>Outpatient attendance</UPI_EVENT_DESC>
  <UPI_EVENT_DATE>2026-03-04</UPI_EVENT_DATE>
</OPI>"""

_PROMS_RFI = """\
<?xml version="1.0" encoding="UTF-8"?>
<RFI>
  <SYSTEM_ID>140</SYSTEM_ID>
  <DHA_CODE>7A7</DHA_CODE>
  <UNIQUE_ID>EPISODE-00456</UNIQUE_ID>
  <NHS_NUMBER>9434765927</NHS_NUMBER>
  <NHS_CERTIFICATION>01</NHS_CERTIFICATION>
  <UNIT_NUMBER>CAV0044556</UNIT_NUMBER>
  <SURNAME>Aneurin</SURNAME>
  <FORENAME>Gareth</FORENAME>
  <SEX>1</SEX>
  <BIRTHDATE>1970-06-21</BIRTHDATE>
  <POSTCODE>CF14 4XW</POSTCODE>
  <SPEC>110</SPEC>
  <SPEC_NAME>Trauma and Orthopaedics</SPEC_NAME>
  <REFERRING_GP>G7654321</REFERRING_GP>
  <UPI_EVENT>OP01</UPI_EVENT>
  <UPI_EVENT_DESC>Outpatient attendance</UPI_EVENT_DESC>
</RFI>"""

_PROMS_MPA = """\
<?xml version="1.0" encoding="UTF-8"?>
<MPA>
  <SYSTEM_ID>108</SYSTEM_ID>
  <DHA_CODE>7A3</DHA_CODE>
  <NHS_NUMBER>9434765919</NHS_NUMBER>
  <NHS_CERTIFICATION>01</NHS_CERTIFICATION>
  <UNIT_NUMBER>SB0099887</UNIT_NUMBER>
  <SURNAME>Bevan</SURNAME>
  <FORENAME>Aneurin</FORENAME>
  <SEX>1</SEX>
  <BIRTHDATE>1897-11-15</BIRTHDATE>
  <POSTCODE>SA1 1AA</POSTCODE>
  <DEATHDATE></DEATHDATE>
</MPA>"""


class PromsPlugin(ServicePlugin):
    tab_label = "PROMS Transformer"
    description = "WPAS XML → PSOM FHIR R4B message Bundle  (OPI / RFI / MPA)"
    input_label = "WPAS XML Input  (OPI / RFI / MPA)"
    output_label = "FHIR R4B JSON Output"
    button_label = "▶  Transform"
    samples = {
        "OPI (Outpatient)": _PROMS_OPI,
        "RFI (Referral)": _PROMS_RFI,
        "MPA (Patient Update)": _PROMS_MPA,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from xml_fhir_proms_transformer.proms_transformer import transform_proms_xml_to_fhir_bundle

        bundle = transform_proms_xml_to_fhir_bundle(input_text.strip())
        raw = bundle.model_dump_json()
        pretty = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)

        entries = [e.resource.get_resource_type() for e in (bundle.entry or [])]
        summary = f"✓  {len(entries)} entries: {', '.join(entries)}"
        return pretty, summary
