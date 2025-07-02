import unittest

from hl7apy.parser import parse_message

from hl7_server.hl7_validator import HL7Validator, ValidationException

# Sample valid HL7 message (pipe & hat, type A28)
VALID_A28_MESSAGE = str.join(
    "",
    [
        "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
        "PID|1||123456^^^Hospital^MR||Doe^John\r"
    ],
)


class TestGenericHandler(unittest.TestCase):
    def test_with_valid_message(self) -> None:
        msg = parse_message(VALID_A28_MESSAGE)
        validator = HL7Validator("2.5", "252")

        validator.validate(msg)

    def test_with_invalid_hl7version(self) -> None:
        msg = parse_message(VALID_A28_MESSAGE)
        validator = HL7Validator("2.3", "252")

        with self.assertRaises(ValidationException):
            validator.validate(msg)

    def test_with_invalid_seding_app(self) -> None:
        msg = parse_message(VALID_A28_MESSAGE)
        validator = HL7Validator("2.5", "101")

        with self.assertRaises(ValidationException):
            validator.validate(msg)

    def test_without_validation(self) -> None:
        msg = parse_message(VALID_A28_MESSAGE)
        validator = HL7Validator()

        validator.validate(msg)
