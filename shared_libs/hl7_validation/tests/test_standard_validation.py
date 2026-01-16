import unittest

from hl7apy.parser import parse_message

from hl7_validation import validate_er7_with_standard, validate_parsed_message_with_standard
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
