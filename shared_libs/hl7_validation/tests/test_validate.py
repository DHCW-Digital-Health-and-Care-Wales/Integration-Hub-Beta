import os
import unittest

from defusedxml import ElementTree as ET
from hl7apy.parser import parse_message

from hl7_validation.convert import er7_to_hl7v2xml
from hl7_validation.schemas import (
    get_schema_xsd_path_for,
    list_schema_groups,
    list_schemas_for_group,
)
from hl7_validation.validate import (
    XmlValidationError,
    validate_er7_with_flow_schema,
    validate_parsed_message_with_flow_schema,
)


class TestSchemaPathResolutionAndTriggerParsing(unittest.TestCase):
    def test_get_schema_xsd_path_for(self) -> None:
        path = get_schema_xsd_path_for("phw", "ADT_A39")
        self.assertTrue(os.path.exists(path))

    def test_validate_uses_built_in_mapping_when_structure_missing(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
            "EVN|A31|20250101010101",
            "PID|||8888888^^^252^PI||SURNAME^FORENAME",
            "PV1||",
        ])

        try:
            validate_er7_with_flow_schema(er7, "phw")
        except XmlValidationError as e:
            self.fail(f"Validation should succeed with fallback: {e}")

    def test_get_schema_xsd_path_for_unknown_flow_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_schema_xsd_path_for("unknown_flow", "ADT_A39")

    def test_schema_groups_and_mappings(self) -> None:
        groups = list_schema_groups()
        self.assertIn("phw", groups)

        mapping = list_schemas_for_group("phw")
        self.assertIn("ADT_A39", mapping)
        path = get_schema_xsd_path_for("phw", "ADT_A39")
        self.assertTrue(os.path.exists(path))

    def test_pid_3_repetitions_emit_multiple_nodes(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|202505052323326666666666|P|2.5",
                "PID|||8888888^^^252^PI~6666666666^^^NHS^NH",
            ]
        )

        struct_path = get_schema_xsd_path_for("phw", "ADT_A05")
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

    def test_parsed_message_flow_validation_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
            "EVN|A31|20250101010101",
            "PID|||8888888^^^252^PI||SURNAME^FORENAME",
            "PV1||",
        ])

        msg = parse_message(er7, find_groups=False)
        validate_parsed_message_with_flow_schema(msg, er7, "phw")

    def test_parsed_message_flow_validation_invalid_raises(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
            "EVN|A31|20250101010101",
        ])

        msg = parse_message(er7, find_groups=False)
        with self.assertRaises(XmlValidationError):
            validate_parsed_message_with_flow_schema(msg, er7, "phw")

    def test_parsed_message_flow_validation_unknown_flow_raises(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
            "EVN|A31|20250101010101",
            "PID|||8888888^^^252^PI||SURNAME^FORENAME",
            "PV1||",
        ])

        msg = parse_message(er7, find_groups=False)
        with self.assertRaises(ValueError):
            validate_parsed_message_with_flow_schema(msg, er7, "unknown_flow")
