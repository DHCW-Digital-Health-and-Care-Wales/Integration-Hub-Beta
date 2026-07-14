import os
import tempfile
import unittest

import xmlschema
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
    _format_schema_validation_error,
    validate_er7_with_flow_schema,
    validate_parsed_message_with_flow_schema,
    validate_xml,
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


class TestSchemaValidationErrorRedaction(unittest.TestCase):
    """Schema validation errors must never leak the XML instance (which contains PII)."""

    # Minimal schema whose <sex> element only accepts M/F, so any other value fails.
    _XSD = (
        '<?xml version="1.0"?>'
        '<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
        '<xsd:element name="patient"><xsd:complexType><xsd:sequence>'
        '<xsd:element name="sex"><xsd:simpleType>'
        '<xsd:restriction base="xsd:string">'
        '<xsd:enumeration value="M"/><xsd:enumeration value="F"/>'
        '</xsd:restriction></xsd:simpleType></xsd:element>'
        '</xsd:sequence></xsd:complexType></xsd:element></xsd:schema>'
    )

    # Instance carrying a fake patient identifier in place of a valid enumeration value.
    _INSTANCE = "<patient><sex>MYSURNAME</sex></patient>"

    def _make_error(self) -> "xmlschema.validators.exceptions.XMLSchemaValidationError":
        schema = xmlschema.XMLSchema(self._XSD)
        try:
            schema.validate(self._INSTANCE)
        except xmlschema.validators.exceptions.XMLSchemaValidationError as e:  # type: ignore[attr-defined]
            return e
        self.fail("Expected schema validation to fail")

    def test_default_str_leaks_instance(self) -> None:
        # Sanity check: the default xmlschema message DOES embed the instance value.
        self.assertIn("MYSURNAME", str(self._make_error()))

    def test_formatter_excludes_instance_pii(self) -> None:
        safe = _format_schema_validation_error(self._make_error())
        self.assertNotIn("MYSURNAME", safe)
        self.assertNotIn("Instance", safe)
        # Still useful for debugging: retains the schema-level reason and the XPath.
        self.assertIn("must be one of", safe)
        self.assertIn("path:", safe)

    def test_validate_xml_raises_without_pii(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xsd_path = os.path.join(tmp, "patient.xsd")
            with open(xsd_path, "w", encoding="utf-8") as fh:
                fh.write(self._XSD)

            with self.assertRaises(XmlValidationError) as ctx:
                validate_xml(self._INSTANCE, xsd_path)

        self.assertNotIn("MYSURNAME", str(ctx.exception))
        self.assertIsNone(ctx.exception.__context__)
