import unittest

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
        self.valid_er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID123|P|2.5",
            "EVN|A31|20250101010101",
            "PID|||8888888^^^252^PI||SURNAME^FORENAME",
            "PV1||",
        ])
        self.invalid_er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID456|P|2.5",
            "EVN|A31|20250101010101",
        ])

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
        er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
            "EVN|A31|20250101010101",
            "PID|||8888888^^^252^PI||SURNAME^FORENAME",
            "PV1||",
        ])
        xml_str = convert_er7_to_xml_with_flow_schema(er7, "phw")

        self.assertIn("<", xml_str)
        self.assertIn("urn:hl7-org:v2xml", xml_str)
        self.assertIn("ADT_A05", xml_str)

    def test_convert_er7_to_xml_invalid_er7_raises(self) -> None:
        with self.assertRaises(XmlValidationError):
            convert_er7_to_xml_with_flow_schema("NOT_VALID_HL7", "phw")

    def test_convert_er7_to_xml_unknown_flow_raises(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
            "EVN|A31|20250101010101",
            "PID|||8888888^^^252^PI||SURNAME^FORENAME",
            "PV1||",
        ])
        with self.assertRaises(ValueError):
            convert_er7_to_xml_with_flow_schema(er7, "unknown_flow")


if __name__ == "__main__":
    unittest.main()
