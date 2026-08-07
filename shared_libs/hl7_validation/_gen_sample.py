from __future__ import annotations

from pathlib import Path

from hl7_validation import convert_er7_to_xml_with_flow_schema, validate_xml
from hl7_validation.schemas import get_schema_xsd_path_for


def main() -> None:
    er7 = chr(13).join(
        [
            "MSH|^~\\&|328|328|100|100|20260729095037||ADT^A28^ADT_A05|6778031837018553261z82215|P|2.5|||AL|NE||UTF-8",
            "EVN|A28|20260729095037",
            "PID|1||B0000010612^^^328^PI||Lims2val^2807261||20010909|M|||"
            "Welsh Parliament^Cardiff Bay^CARDIFF^^CF99 1SN",
            "PD1|||^^UNK|UNK",
            "PV1||N",
        ]
    )

    xml_payload = convert_er7_to_xml_with_flow_schema(er7, "phw")
    validate_xml(xml_payload, get_schema_xsd_path_for("phw", "ADT_A05"))

    soap = (
        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
        "<SOAP-ENV:Body>"
        + xml_payload
        + "</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    )

    repo_root = Path(__file__).resolve().parents[2]
    out_path = repo_root / "local" / "sample_messages" / "lims-to-mpi.sample.xml"
    out_path.write_text(soap, encoding="utf-8")
    print("OK, length:", len(soap), "written to:", out_path)


if __name__ == "__main__":
    main()
