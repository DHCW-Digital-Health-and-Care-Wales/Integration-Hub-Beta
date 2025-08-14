import os
import unittest
import xml.etree.ElementTree as ET

from hl7_validation.convert import er7_to_hl7v2xml
from hl7_validation import get_schema_xsd_path_for


class TestConvertAndWriteFile(unittest.TestCase):
    def test_convert_er7_to_xml_and_write_file(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:30||ADT^A31^ADT_A05|202505052323300000000000|P|2.5|||||GBR||EN",
                "EVN|A05|20250502092900|20250505232330|||20250505232330",
                "PID|||8888888^^^252^PI~4444444444^^^NHS^NH||SURNAME^FORENAME",
                "PV1||",
            ]
        )

        structure_xsd_path = get_schema_xsd_path_for("phw", "A05")
        xml_str = er7_to_hl7v2xml(er7, structure_xsd_path=structure_xsd_path)

        out_dir = os.path.join(os.path.dirname(__file__), "_artifacts")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, "phw_a05_converted.xml")

        with open(out_file, "w", encoding="utf-8") as f:
            f.write(xml_str)

        self.assertTrue(os.path.exists(out_file))

        root = ET.fromstring(xml_str)
        self.assertTrue(root.tag.endswith("}ADT_A05") or root.tag == "ADT_A05")