import unittest

from defusedxml import ElementTree as ET
from hl7apy.parser import parse_message

from hl7_validation import (
    ValidationResult,
    XmlValidationError,
    convert_er7_to_xml_with_flow_schema,
    validate_and_convert_er7_with_flow_schema,
    validate_and_convert_parsed_message_with_flow_schema,
)


class TestValidationResult(unittest.TestCase):
    def test_validation_result_bool_true_when_valid(self) -> None:
        result = ValidationResult(
            xml_string="<test/>",
            structure_id="ADT_A05",
            is_valid=True,
        )
        self.assertTrue(result)
        self.assertTrue(result.is_valid)

    def test_validation_result_bool_false_when_invalid(self) -> None:
        result = ValidationResult(
            xml_string="<test/>",
            structure_id="ADT_A05",
            is_valid=False,
            error_message="Test error",
        )
        self.assertFalse(result)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_message, "Test error")


class TestValidateAndConvert(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_er7 = "\r".join(
            [
                "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID123|P|2.5",
                "EVN|A31|20250101010101",
                "PID|||8888888^^^252^PI||SURNAME^FORENAME",
                "PV1||",
            ]
        )
        self.invalid_er7 = "\r".join(
            [
                "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID456|P|2.5",
                "EVN|A31|20250101010101",
            ]
        )

    def test_validate_and_convert_valid_message(self) -> None:
        result = validate_and_convert_er7_with_flow_schema(self.valid_er7, "phw")

        self.assertTrue(result.is_valid)
        self.assertIsNone(result.error_message)
        self.assertIn("ADT_A05", result.structure_id)
        self.assertEqual(result.message_type, "ADT")
        self.assertEqual(result.trigger_event, "A31")
        self.assertEqual(result.message_control_id, "MSGID123")
        self.assertIn("<", result.xml_string)
        self.assertIn("urn:hl7-org:v2xml", result.xml_string)

    def test_validate_and_convert_invalid_message_returns_result_with_error(self) -> None:
        result = validate_and_convert_er7_with_flow_schema(self.invalid_er7, "phw")

        self.assertFalse(result.is_valid)
        self.assertIsNotNone(result.error_message)
        self.assertIn("ADT_A05", result.structure_id)
        self.assertEqual(result.message_control_id, "MSGID456")
        self.assertIn("<", result.xml_string)

    def test_validate_and_convert_invalid_er7_raises(self) -> None:
        with self.assertRaises(XmlValidationError):
            validate_and_convert_er7_with_flow_schema("NOT_VALID_HL7", "phw")

    def test_validate_and_convert_parsed_message_valid(self) -> None:
        msg = parse_message(self.valid_er7, find_groups=False)
        result = validate_and_convert_parsed_message_with_flow_schema(msg, self.valid_er7, "phw")

        self.assertTrue(result.is_valid)
        self.assertEqual(result.message_control_id, "MSGID123")

    def test_validate_and_convert_parsed_message_invalid(self) -> None:
        msg = parse_message(self.invalid_er7, find_groups=False)
        result = validate_and_convert_parsed_message_with_flow_schema(msg, self.invalid_er7, "phw")

        self.assertFalse(result.is_valid)
        self.assertIsNotNone(result.error_message)


class TestConvertWithoutValidation(unittest.TestCase):
    def test_convert_er7_to_xml_returns_xml_string(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
                "EVN|A31|20250101010101",
                "PID|||8888888^^^252^PI||SURNAME^FORENAME",
                "PV1||",
            ]
        )
        xml_str = convert_er7_to_xml_with_flow_schema(er7, "phw")

        self.assertIn("<", xml_str)
        self.assertIn("urn:hl7-org:v2xml", xml_str)
        self.assertIn("ADT_A05", xml_str)

    def test_convert_er7_to_xml_invalid_er7_raises(self) -> None:
        with self.assertRaises(XmlValidationError):
            convert_er7_to_xml_with_flow_schema("NOT_VALID_HL7", "phw")

    def test_convert_er7_to_xml_unknown_flow_raises(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
                "EVN|A31|20250101010101",
                "PID|||8888888^^^252^PI||SURNAME^FORENAME",
                "PV1||",
            ]
        )
        with self.assertRaises(ValueError):
            convert_er7_to_xml_with_flow_schema(er7, "unknown_flow")


class TestConvertEr7ToXmlComprehensive(unittest.TestCase):
    """Comprehensive test of convert_er7_to_xml with full field assertions"""

    def test_convert_er7_to_xml_comprehensive_field_mapping(self) -> None:
        """Test complete ER7 to XML conversion with all message fields"""
        er7_message = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505444444|P|2.5|||||GBR||EN",
                "EVN||20250502092900|20250505232332|||20250505232332",
                "PID|||8888888^^^252^PI~4444444444^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19990101|M|||"
                "99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H~"
                "SECOND1^SECOND2^SECOND3^SECOND4^SB99 9SB^^H||||||||||||||||||2024-12-31|||01",
                "PD1|||^^W00000|G999999",
                "PV1||U",
            ]
        )

        # Use flow schema conversion (convert_er7_to_xml requires XSD files)
        xml_string = convert_er7_to_xml_with_flow_schema(er7_message, "phw")

        # Parse XML
        root = ET.fromstring(xml_string)
        ns = {"hl7": "urn:hl7-org:v2xml"}

        # Helper to get text from XML element
        def get_text(xpath: str) -> str | None:
            elem = root.find(xpath, ns)
            return elem.text if elem is not None else None

        # MSH Segment Assertions
        msh = root.find(".//hl7:MSH", ns)
        self.assertIsNotNone(msh, "MSH segment should exist")

        # MSH-1: Field Separator
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.1"), "|")

        # MSH-2: Encoding Characters
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.2"), "^~\\&")

        # MSH-3: Sending Application
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.3/hl7:HD.1"), "252")

        # MSH-4: Sending Facility
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.4/hl7:HD.1"), "252")

        # MSH-5: Receiving Application
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.5/hl7:HD.1"), "100")

        # MSH-6: Receiving Facility
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.6/hl7:HD.1"), "100")

        # MSH-7: Timestamp
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.7/hl7:TS.1"), "2025-05-05 23:23:32")

        # MSH-9: Message Type
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.9/hl7:MSG.1"), "ADT")
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.9/hl7:MSG.2"), "A31")
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.9/hl7:MSG.3"), "ADT_A05")

        # MSH-10: Message Control ID
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.10"), "202505444444")

        # MSH-11: Processing ID
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.11/hl7:PT.1"), "P")

        # MSH-12: Version ID
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.12/hl7:VID.1"), "2.5")

        # MSH-17: Country Code
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.17"), "GBR")

        # MSH-19: Principal Language of Message
        self.assertEqual(get_text(".//hl7:MSH/hl7:MSH.19/hl7:CE.1"), "EN")

        # EVN Segment Assertions
        evn = root.find(".//hl7:EVN", ns)
        self.assertIsNotNone(evn, "EVN segment should exist")

        # EVN-2: Recorded Date/Time
        self.assertEqual(get_text(".//hl7:EVN/hl7:EVN.2/hl7:TS.1"), "20250502092900")

        # EVN-3: Date/Time Planned Event
        self.assertEqual(get_text(".//hl7:EVN/hl7:EVN.3/hl7:TS.1"), "20250505232332")

        # EVN-6: Event Occurred
        self.assertEqual(get_text(".//hl7:EVN/hl7:EVN.6/hl7:TS.1"), "20250505232332")

        # PID Segment Assertions
        pid = root.find(".//hl7:PID", ns)
        self.assertIsNotNone(pid, "PID segment should exist")

        # PID-3: Patient Identifier List (repeating field - two identifiers)
        pid_3_repeats = root.findall(".//hl7:PID/hl7:PID.3", ns)
        self.assertEqual(len(pid_3_repeats), 2, "Should have 2 patient identifiers")

        # First identifier: 8888888^^^252^PI
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.3[1]/hl7:CX.1"), "8888888")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.3[1]/hl7:CX.4/hl7:HD.1"), "252")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.3[1]/hl7:CX.5"), "PI")

        # Second identifier: 4444444444^^^NHS^NH
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.3[2]/hl7:CX.1"), "4444444444")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.3[2]/hl7:CX.4/hl7:HD.1"), "NHS")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.3[2]/hl7:CX.5"), "NH")

        # PID-5: Patient Name - MYSURNAME^MYFNAME^MYMNAME^^MR
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.5/hl7:XPN.1/hl7:FN.1"), "MYSURNAME")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.5/hl7:XPN.2"), "MYFNAME")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.5/hl7:XPN.3"), "MYMNAME")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.5/hl7:XPN.5"), "MR")

        # PID-7: Date of Birth
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.7/hl7:TS.1"), "19990101")

        # PID-8: Administrative Sex
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.8"), "M")

        # PID-11: Patient Address (repeating - two addresses)
        pid_11_repeats = root.findall(".//hl7:PID/hl7:PID.11", ns)
        self.assertEqual(len(pid_11_repeats), 2, "Should have 2 addresses")

        # First address: 99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[1]/hl7:XAD.1/hl7:SAD.1"), "99, MY ROAD")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[1]/hl7:XAD.2"), "MY PLACE")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[1]/hl7:XAD.3"), "MY CITY")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[1]/hl7:XAD.4"), "MY COUNTY")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[1]/hl7:XAD.5"), "SA99 1XX")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[1]/hl7:XAD.7"), "H")

        # Second address: SECOND1^SECOND2^SECOND3^SECOND4^SB99 9SB^^H
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[2]/hl7:XAD.1/hl7:SAD.1"), "SECOND1")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[2]/hl7:XAD.2"), "SECOND2")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[2]/hl7:XAD.3"), "SECOND3")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[2]/hl7:XAD.4"), "SECOND4")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[2]/hl7:XAD.5"), "SB99 9SB")
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.11[2]/hl7:XAD.7"), "H")

        # PID-29: Patient Death Date
        self.assertEqual(get_text(".//hl7:PID/hl7:PID.29/hl7:TS.1"), "2024-12-31")

        # Note: PID.31 and later trailing fields may not be included in XML
        # if they follow many empty fields, depending on the conversion logic

        # PD1 Segment Assertions
        pd1 = root.find(".//hl7:PD1", ns)
        self.assertIsNotNone(pd1, "PD1 segment should exist")

        # PD1-3: Patient Primary Facility - ^^W00000
        self.assertEqual(get_text(".//hl7:PD1/hl7:PD1.3/hl7:XON.3"), "W00000")

        # PD1-4: Patient Primary Care Provider - G999999
        self.assertEqual(get_text(".//hl7:PD1/hl7:PD1.4/hl7:XCN.1"), "G999999")

        # PV1 Segment Assertions
        pv1 = root.find(".//hl7:PV1", ns)
        self.assertIsNotNone(pv1, "PV1 segment should exist")

        # PV1-2: Patient Class
        self.assertEqual(get_text(".//hl7:PV1/hl7:PV1.2"), "U")

        # Verify XML is well-formed and contains namespace
        self.assertIn("urn:hl7-org:v2xml", xml_string)
        self.assertIn("<", xml_string)
        self.assertTrue(xml_string.strip().startswith("<?xml") or xml_string.strip().startswith("<"))


if __name__ == "__main__":
    unittest.main()
