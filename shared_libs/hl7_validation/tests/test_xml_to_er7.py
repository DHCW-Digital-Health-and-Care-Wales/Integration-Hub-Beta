import unittest

from hl7_validation import convert_er7_to_xml_with_flow_schema
from hl7_validation.convert import convert_er7_to_xml, xml_to_er7


class TestXmlToEr7PreservesPositionalComponents(unittest.TestCase):
    """
    Regression tests for xml_to_er7 positional-component handling.

    HL7v2 XML names every component/sub-component by position (CX.1, CX.4,
    HD.1, ...). An earlier implementation dropped empty children, which shifted
    later components left and silently corrupted data such as the PID-3 CX.4
    assigning authority (``B0000010612^^^328^PI`` collapsed to
    ``B0000010612^328^PI``). These tests lock in that internal empties are kept
    and only trailing empties are trimmed.
    """

    NS = "urn:hl7-org:v2xml"

    def _xml(self, body: str) -> str:
        return f'<ORU_R01 xmlns="{self.NS}">{body}</ORU_R01>'

    def test_internal_empty_components_preserved(self) -> None:
        # PID.3 with empty CX.2/CX.3 and the assigning authority in CX.4.
        xml = self._xml(
            "<PID><PID.3>"
            "<CX.1>B0000010612</CX.1><CX.2/><CX.3/>"
            "<CX.4><HD.1>328</HD.1><HD.2/><HD.3/></CX.4>"
            "<CX.5>PI</CX.5>"
            "</PID.3></PID>"
        )

        er7 = xml_to_er7(xml)

        self.assertEqual(er7, "PID|||B0000010612^^^328^PI")

    def test_trailing_empty_components_trimmed(self) -> None:
        xml = self._xml(
            "<PID><PID.3>"
            "<CX.1>A</CX.1><CX.2>B</CX.2><CX.3/><CX.4/>"
            "</PID.3></PID>"
        )

        er7 = xml_to_er7(xml)

        # Trailing empty CX.3/CX.4 are dropped, internal values preserved.
        self.assertEqual(er7, "PID|||A^B")

    def test_subcomponents_joined_with_ampersand(self) -> None:
        # Two populated HD sub-components inside CX.4 must use the '&' separator
        # when the field is serialised back to ER7.
        xml = self._xml(
            "<PID><PID.3>"
            "<CX.1>B0000010612</CX.1><CX.2/><CX.3/>"
            "<CX.4><HD.1>328</HD.1><HD.2>X</HD.2><HD.3/></CX.4>"
            "<CX.5>PI</CX.5>"
            "</PID.3></PID>"
        )

        er7 = xml_to_er7(xml)

        self.assertEqual(er7, "PID|||B0000010612^^^328&X^PI")

    def test_round_trip_preserves_pid3_assigning_authority(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|328|328|200|200|20250101120000||ADT^A31^ADT_A05|"
                "CTRL1|P|2.5|||||GBR||EN",
                "EVN||20250101120000",
                "PID|1||B0000010612^^^328^PI~9876543210^^^NHS^NH||"
                "Lims2val^Test||20010909|M",
                "PV1||U",
            ]
        )

        xml = convert_er7_to_xml_with_flow_schema(er7, "phw")
        round_tripped = xml_to_er7(xml)

        pid = next(line for line in round_tripped.split("\r") if line.startswith("PID"))
        self.assertIn("B0000010612^^^328^PI", pid)
        self.assertIn("9876543210^^^NHS^NH", pid)

    def test_schemaless_round_trip_preserves_internal_empties(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|20250505232330||ADT^A31^ADT_A05|"
                "CTRL2|P|2.5|||||GBR||EN",
                "EVN||20250505232330",
                "PID|1||8888888^^^252^PI~4444444444^^^NHS^NH||Test^Patient||20000101|M",
                "PV1||U",
            ]
        )

        xml = convert_er7_to_xml(er7)
        round_tripped = xml_to_er7(xml)

        pid = next(line for line in round_tripped.split("\r") if line.startswith("PID"))
        self.assertIn("8888888^^^252^PI", pid)
        self.assertIn("4444444444^^^NHS^NH", pid)


if __name__ == "__main__":
    unittest.main()
