import os
import unittest
from defusedxml import ElementTree as ET

from hl7_validation import (
    list_schema_groups,
    list_schemas_for_group,
    get_schema_xsd_path_for,
)


class TestExampleMessages(unittest.TestCase):
    def test_schema_groups_and_mappings(self) -> None:
        groups = list_schema_groups()
        self.assertIn("phw", groups)

        mapping = list_schemas_for_group("phw")
        self.assertIn("A39", mapping)
        path = get_schema_xsd_path_for("phw", "A39")
        self.assertTrue(os.path.exists(path))

    def test_pid_3_repetitions_emit_multiple_nodes(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|202505052323326666666666|P|2.5",
                "PID|||8888888^^^252^PI~6666666666^^^NHS^NH",
            ]
        )
        from hl7_validation.convert import er7_to_hl7v2xml
        from hl7_validation import get_schema_xsd_path_for

        struct_path = get_schema_xsd_path_for("phw", "A05")
        xml_str = er7_to_hl7v2xml(er7, structure_xsd_path=struct_path)
        root = ET.fromstring(xml_str)
        NS = {"v2": "urn:hl7-org:v2xml"}
        pid_nodes = root.findall(".//v2:PID", namespaces=NS)
        self.assertEqual(len(pid_nodes), 1)
        pid3_nodes = pid_nodes[0].findall("v2:PID.3", namespaces=NS)
        self.assertEqual(len(pid3_nodes), 2)
        
        cx1_1 = pid3_nodes[0].findtext("v2:CX.1", namespaces=NS)
        hd1_1 = pid3_nodes[0].findtext("v2:CX.4/v2:HD.1", namespaces=NS)
        cx5_1 = pid3_nodes[0].findtext("v2:CX.5", namespaces=NS)
        self.assertEqual(cx1_1, "8888888")
        self.assertEqual(hd1_1, "252")
        self.assertEqual(cx5_1, "PI")

        cx1_2 = pid3_nodes[1].findtext("v2:CX.1", namespaces=NS)
        hd1_2 = pid3_nodes[1].findtext("v2:CX.4/v2:HD.1", namespaces=NS)
        cx5_2 = pid3_nodes[1].findtext("v2:CX.5", namespaces=NS)
        self.assertEqual(cx1_2, "6666666666")
        self.assertEqual(hd1_2, "NHS")
        self.assertEqual(cx5_2, "NH")

    def test_phw_a39_convert_and_validate(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A28^ADT_A39||P|2.5|||||GBR||EN",
                "EVN|A39|20250502092900|20250505232332|||20250505232332",
                "PID|||8888888^^^252^PI~4444444444^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19990101|M|^^||99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H~^^^^^^||^^^~|||||||||||||||||||01",
                "PD1|||^^W00000^|G999999",
                "MRG|||7777777^^^252^PI~5555555555^^^NHS^NH",
                "PV1||",
            ]
        )

        from hl7_validation import validate_er7_with_flow

        validate_er7_with_flow(er7, "phw")

    def test_phw_a05_convert_and_validate(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:30||ADT^A31^ADT_A05|202505052323300000000000|P|2.5|||||GBR||EN",
                "EVN|A05|20250502092900|20250505232330|||20250505232330",
                "PID|||8888888^^^252^PI~4444444444^^^NHS^NH||SURNAME^FORENAME",
                "PV1||",
            ]
        )

        from hl7_validation import validate_er7_with_flow

        validate_er7_with_flow(er7, "phw")

    def test_chemo_a05_convert_and_validate(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|212|212|200|200|20250701140735||ADT^A31|201600952808665|P|2.4|||NE|NE EVN|Sub|20250701140735",
                "PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^T^^Mrs.||20000101000000|F|||TEST,^TEST^TEST TEST^^CF11 9AD||01000 000 001|07000000001||||||||||||||||||0",
                "PD1||||G7000001",
                "PV1||U",
            ]
        )

        from hl7_validation import validate_er7_with_flow

        validate_er7_with_flow(er7, "chemo")