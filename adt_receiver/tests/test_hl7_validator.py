import unittest

from hl7apy.parser import parse_message

from adt_receiver.exceptions.validation_exception import ValidationException
from adt_receiver.hl7_validator import HL7Validator

VALID_ADT_A01 = (
    "MSH|^~\\&|SENDER|FACILITY|RECEIVER|DEST|20250506120000||ADT^A01^ADT_A01|MSG001|P|2.5\r"
    "PID|1||12345^^^Hospital^MR||Smith^John\r"
)

VALID_ADT_A28 = (
    "MSH|^~\\&|SENDER|FACILITY|RECEIVER|DEST|20250506120000||ADT^A28^ADT_A05|MSG002|P|2.5\r"
    "PID|1||67890^^^Hospital^MR||Doe^Jane\r"
)

NON_ADT_MESSAGE = (
    "MSH|^~\\&|SENDER|FACILITY|RECEIVER|DEST|20250506120000||ORU^R01|MSG003|P|2.5\r"
    "PID|1||99999^^^Hospital^MR||Jones^Bob\r"
)


class TestHl7Validator(unittest.TestCase):

    def test_valid_adt_a01_passes(self) -> None:
        validator = HL7Validator()
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        validator.validate(msg)  # Should not raise

    def test_valid_adt_a28_passes(self) -> None:
        validator = HL7Validator()
        msg = parse_message(VALID_ADT_A28, find_groups=False)
        validator.validate(msg)  # Should not raise

    def test_non_adt_message_raises_validation_exception(self) -> None:
        validator = HL7Validator()
        msg = parse_message(NON_ADT_MESSAGE, find_groups=False)
        with self.assertRaises(ValidationException) as ctx:
            validator.validate(msg)
        self.assertIn("ORU", str(ctx.exception))

    def test_wrong_hl7_version_raises_validation_exception(self) -> None:
        validator = HL7Validator(hl7_version="2.5.1")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        with self.assertRaises(ValidationException) as ctx:
            validator.validate(msg)
        self.assertIn("version", str(ctx.exception))

    def test_correct_hl7_version_passes(self) -> None:
        validator = HL7Validator(hl7_version="2.5")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        validator.validate(msg)  # Should not raise

    def test_multiple_allowed_versions_accepts_matching(self) -> None:
        validator = HL7Validator(hl7_version="2.4, 2.5, 2.5.1")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        validator.validate(msg)  # 2.5 is in the list, should not raise

    def test_multiple_allowed_versions_rejects_non_matching(self) -> None:
        validator = HL7Validator(hl7_version="2.4, 2.3")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        with self.assertRaises(ValidationException) as ctx:
            validator.validate(msg)
        self.assertIn("2.5", str(ctx.exception))

    def test_wrong_sending_app_raises_validation_exception(self) -> None:
        validator = HL7Validator(sending_app="ALLOWED_APP")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        with self.assertRaises(ValidationException) as ctx:
            validator.validate(msg)
        self.assertIn("SENDER", str(ctx.exception))

    def test_correct_sending_app_passes(self) -> None:
        validator = HL7Validator(sending_app="SENDER")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        validator.validate(msg)  # Should not raise

    def test_multiple_allowed_sending_apps(self) -> None:
        validator = HL7Validator(sending_app="APP1, SENDER, APP2")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        validator.validate(msg)  # Should not raise

    def test_no_version_or_sending_app_configured_accepts_any(self) -> None:
        validator = HL7Validator()
        msg = parse_message(VALID_ADT_A28, find_groups=False)
        validator.validate(msg)  # Should not raise

    def test_message_type_whitelist_accepts_matching_trigger_event(self) -> None:
        validator = HL7Validator(message_type="A01,A28,A31")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        validator.validate(msg)  # A01 is in the list, should not raise

    def test_message_type_whitelist_rejects_non_matching_trigger_event(self) -> None:
        validator = HL7Validator(message_type="A28,A31")
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        with self.assertRaises(ValidationException) as ctx:
            validator.validate(msg)
        self.assertIn("A01", str(ctx.exception))

    def test_message_type_not_set_accepts_any_trigger_event(self) -> None:
        validator = HL7Validator()
        msg = parse_message(VALID_ADT_A01, find_groups=False)
        validator.validate(msg)  # No whitelist => any ADT trigger event is accepted


if __name__ == "__main__":
    unittest.main()
