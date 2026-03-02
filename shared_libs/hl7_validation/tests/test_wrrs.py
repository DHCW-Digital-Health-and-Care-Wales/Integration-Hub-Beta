import unittest

from defusedxml import ElementTree as ET

from hl7_validation.convert import er7_to_hl7v2xml
from hl7_validation.schemas import get_schema_xsd_path_for


class TestWrrsMessages(unittest.TestCase):
    def test_wrrs_oru_r01_conversion_handles_standalone_schema(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|SNDAPP|SNDFAC|RCVAPP|RCVFAC|20250101010101||ORU^R01|12345|P|2.5",
                "PID|1||123456^^^HOSP^MR||DOE^JANE||19900101|F",
                "PV1|1|O",
                "ORC|RE|ORD001",
                "OBR|1|ORD001||TEST^Panel",
                "OBX|1|ST|CODE^Result||Normal",
            ]
        )

        struct_path = get_schema_xsd_path_for("wrrs", "ORU_R01")
        xml_str = er7_to_hl7v2xml(
            er7, structure_xsd_path=struct_path, override_structure_id="ORU_R01"
        )

        root = ET.fromstring(xml_str)
        NS = {"v2": "urn:hl7-org:v2xml"}
        self.assertEqual(root.tag, "{urn:hl7-org:v2xml}ORU_R01")
        self.assertIsNotNone(root.find(".//v2:MSH/v2:MSH.3/v2:HD.1", namespaces=NS))

    def test_wrrs_repeating_obx_creates_repeating_observation_groups(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|SNDAPP|SNDFAC|RCVAPP|RCVFAC|20250101010101||ORU^R01|12345|P|2.5",
                "PID|1||123456^^^HOSP^MR||DOE^JANE||19900101|F",
                "PV1|1|O",
                "ORC|RE|ORD001",
                "OBR|1|ORD001||TEST^Panel",
                "OBX|1|ST|CODE1^Result1||Normal",
                "OBX|2|ST|CODE2^Result2||Raised",
            ]
        )

        struct_path = get_schema_xsd_path_for("wrrs", "ORU_R01")
        xml_str = er7_to_hl7v2xml(
            er7, structure_xsd_path=struct_path, override_structure_id="ORU_R01"
        )
        root = ET.fromstring(xml_str)
        NS = {"v2": "urn:hl7-org:v2xml"}

        observation_nodes = root.findall(
            ".//v2:ORU_R01.OBSERVATION", namespaces=NS
        )
        self.assertGreaterEqual(len(observation_nodes), 2)
