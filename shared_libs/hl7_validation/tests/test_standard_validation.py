import unittest

from hl7apy.parser import parse_message

from hl7_validation import validate_er7_with_standard, validate_parsed_message_with_standard
from hl7_validation.standard_validate import validate_xml_with_hl7apy
from hl7_validation.validate import XmlValidationError


class TestStandardValidation(unittest.TestCase):
    def test_standard_validation_v25_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        validate_er7_with_standard(er7, "2.5")

    def test_standard_validation_v251_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5.1",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        validate_er7_with_standard(er7, "2.5.1")

    def test_standard_validation_v24_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.4",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        validate_er7_with_standard(er7, "2.4")

    def test_standard_validation_v26_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.6",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        validate_er7_with_standard(er7, "2.6")


    def test_standard_validation_invalid_version_raises(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_standard(er7, "2.9")
        error_message = str(context.exception)
        self.assertIn("Unsupported HL7 version", error_message)

    def test_standard_validation_malformed_message_raises(self) -> None:
        er7 = "This is not a valid HL7 message"

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_standard(er7, "2.5")
        error_message = str(context.exception)
        self.assertIn("Unable to parse ER7 message", error_message)

    def test_parsed_message_standard_validation_v25_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        msg = parse_message(er7, find_groups=False)
        validate_parsed_message_with_standard(msg, "2.5")

    def test_parsed_message_standard_validation_v251_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5.1",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        msg = parse_message(er7, find_groups=False)
        validate_parsed_message_with_standard(msg, "2.5.1")

    def test_parsed_message_standard_validation_v24_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.4",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        msg = parse_message(er7, find_groups=False)
        validate_parsed_message_with_standard(msg, "2.4")

    def test_parsed_message_standard_validation_v26_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.6",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        msg = parse_message(er7, find_groups=False)
        validate_parsed_message_with_standard(msg, "2.6")


    def test_parsed_message_standard_validation_invalid_version_raises(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        msg = parse_message(er7, find_groups=False)
        with self.assertRaises(XmlValidationError) as context:
            validate_parsed_message_with_standard(msg, "2.9")
        error_message = str(context.exception)
        self.assertIn("Unsupported HL7 version", error_message)

    def test_parsed_message_standard_validation_version_mismatch_raises(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5",
            "EVN|A05|20250101010101",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
            "PV1||I",
        ])

        msg = parse_message(er7, find_groups=False)
        with self.assertRaises(XmlValidationError) as context:
            validate_parsed_message_with_standard(msg, "2.4")
        error_message = str(context.exception)
        self.assertIn("Message version 2.5 does not match requested version 2.4", error_message)

    def test_standard_validation_missing_required_segment_raises(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SENDER|FACILITY|RECEIVER|FACILITY|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5",
            "PID|||123456^^^MR||DOE^JOHN||19800101|M",
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_standard(er7, "2.5")
        error_message = str(context.exception)
        self.assertIn("Standard HL7 v2.5 validation failed", error_message)


class TestXmlValidationWithHl7apy(unittest.TestCase):
    """Tests for validate_xml_with_hl7apy function."""

    def _create_valid_xml(self, version: str) -> str:
        """Helper to create a valid HL7v2 XML message."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<ADT_A05 xmlns="urn:hl7-org:v2xml">
    <MSH>
        <MSH.1>|</MSH.1>
        <MSH.2>^~\\&amp;</MSH.2>
        <MSH.3>SENDER</MSH.3>
        <MSH.4>FACILITY</MSH.4>
        <MSH.5>RECEIVER</MSH.5>
        <MSH.6>FACILITY</MSH.6>
        <MSH.7>20250101010101</MSH.7>
        <MSH.9>
            <MSG.1>ADT</MSG.1>
            <MSG.2>A05</MSG.2>
            <MSG.3>ADT_A05</MSG.3>
        </MSH.9>
        <MSH.10>MSG123</MSH.10>
        <MSH.11>P</MSH.11>
        <MSH.12>{version}</MSH.12>
    </MSH>
    <EVN>
        <EVN.1>A05</EVN.1>
        <EVN.2>20250101010101</EVN.2>
    </EVN>
    <PID>
        <PID.3>123456^^^MR</PID.3>
        <PID.5>
            <XPN.1>DOE</XPN.1>
            <XPN.2>JOHN</XPN.2>
        </PID.5>
        <PID.7>19800101</PID.7>
        <PID.8>M</PID.8>
    </PID>
    <PV1>
        <PV1.2>I</PV1.2>
    </PV1>
</ADT_A05>"""

    def test_xml_validation_successful_for_supported_versions(self) -> None:
        for version in ("2.4", "2.5", "2.5.1", "2.6"):
            with self.subTest(version=version):
                xml = self._create_valid_xml(version)
                validate_xml_with_hl7apy(xml, version)

    def test_xml_validation_invalid_version_raises(self) -> None:
        xml = self._create_valid_xml("2.5")

        with self.assertRaises(XmlValidationError) as context:
            validate_xml_with_hl7apy(xml, "2.9")
        error_message = str(context.exception)
        self.assertIn("Unsupported HL7 version", error_message)

    def test_xml_validation_invalid_xml_raises(self) -> None:
        invalid_xml = "This is not valid XML"

        with self.assertRaises(XmlValidationError) as context:
            validate_xml_with_hl7apy(invalid_xml, "2.5")
        error_message = str(context.exception)
        self.assertIn("Failed to convert XML to ER7", error_message)

    def test_xml_validation_malformed_xml_raises(self) -> None:
        malformed_xml = "<ADT_A05><MSH><MSH.1>|</MSH.1></MSH>"  # Missing closing tag

        with self.assertRaises(XmlValidationError) as context:
            validate_xml_with_hl7apy(malformed_xml, "2.5")
        error_message = str(context.exception)
        self.assertIn("Failed to convert XML to ER7", error_message)
