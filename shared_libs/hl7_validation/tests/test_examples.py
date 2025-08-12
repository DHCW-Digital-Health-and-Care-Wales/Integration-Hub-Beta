import unittest
import xml.etree.ElementTree as ET

from hl7_validation import er7_to_xml, validate_xml, get_schema_xsd_path


class TestExampleMessages(unittest.TestCase):
    def setUp(self) -> None:
        self.xsd_path = get_schema_xsd_path("phw_schema")

    def test_example_a28_validates(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|202505052323326666666666|P|2.5|||||GBR||EN",
                "EVN||20250502102000|20250505232328|||20250505232328",
                "PID|||8888888^^^252^PI~6666666666^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19870101|M|^^||ADDRESS1^ADDRESS2^ADDRESS3^ADDRESS4^XX99 9XX^^H~^^^^^^||^^^~|||||||||||||||||||01",
                "PD1|||^^W99999^|G7777777",
                "PV1||",
            ]
        )
        xml_str = er7_to_xml(er7)
        validate_xml(xml_str, self.xsd_path)

    def test_example_a31_validates(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444444444|P|2.5|||||GBR||EN",
                "EVN||20250502092900|20250505232332|||20250505232332",
                "PID|||8888888^^^252^PI~4444444444^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19990101|M|^^||99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H~^^^^^^||^^^~|||||||||||||||||||01",
                "PD1|||^^W00000^|G999999",
                "PV1||",
            ]
        )
        xml_str = er7_to_xml(er7)
        validate_xml(xml_str, self.xsd_path)

    def test_pid_3_repetitions_emit_multiple_nodes(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|202505052323326666666666|P|2.5",
                "PID|||8888888^^^252^PI~6666666666^^^NHS^NH",
            ]
        )
        xml_str = er7_to_xml(er7)
        root = ET.fromstring(xml_str)
        pid_nodes = root.findall("PID")
        self.assertEqual(len(pid_nodes), 1)
        pid3_nodes = pid_nodes[0].findall("PID.3")
        values = [n.text for n in pid3_nodes]
        self.assertEqual(len(values), 2)
        self.assertIn("8888888^^^252^PI", values)
        self.assertIn("6666666666^^^NHS^NH", values)


if __name__ == "__main__":
    unittest.main()


