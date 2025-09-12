import unittest

from hl7apy.parser import parse_message

from hl7_pharmacy_transformer.pharmacy_transformer import transform_pharmacy_message, validate_assigning_authority
from tests.pharmacy_messages import pharmacy_messages


class TestPharmacyTransformer(unittest.TestCase):

    def test_validate_assigning_authority_valid_cases(self) -> None:
        valid_test_cases = [
            ("valid_assigning_authority_108", "108"),
            ("valid_assigning_authority_310", "310"),
        ]

        for message_key, expected_authority in valid_test_cases:
            with self.subTest(message_key=message_key):
                hl7_message = parse_message(pharmacy_messages[message_key])
                result = validate_assigning_authority(hl7_message)
                self.assertTrue(result, f"Message {message_key} should be valid")

    def test_validate_assigning_authority_invalid_cases(self) -> None:
        invalid_cases = [
            "invalid_assigning_authority_999",
            "empty_assigning_authority",
        ]

        for message_key in invalid_cases:
            with self.subTest(message_key=message_key):
                hl7_message = parse_message(pharmacy_messages[message_key])
                result = validate_assigning_authority(hl7_message)
                self.assertFalse(result, f"Message {message_key} should be invalid")

    def test_validate_assigning_authority_missing_segments(self) -> None:
        missing_cases = [
            "missing_pid_segment",
            "missing_pid3_field",
        ]

        for message_key in missing_cases:
            with self.subTest(message_key=message_key):
                hl7_message = parse_message(pharmacy_messages[message_key])
                result = validate_assigning_authority(hl7_message)
                self.assertFalse(result, f"Message {message_key} should be invalid due to missing fields")

    def test_transform_pharmacy_message_valid_authority(self) -> None:
        valid_message_keys = [
            "valid_assigning_authority_108",
            "valid_assigning_authority_310",
        ]

        for message_key in valid_message_keys:
            with self.subTest(message_key=message_key):
                hl7_message = parse_message(pharmacy_messages[message_key])
                result = transform_pharmacy_message(hl7_message)

                self.assertIsNotNone(result)
                self.assertEqual(result.version, hl7_message.version)
                self.assertIsNotNone(result.msh)

    def test_transform_pharmacy_message_invalid_authority(self) -> None:
        invalid_message_keys = [
            "invalid_assigning_authority_999",
        ]

        for message_key in invalid_message_keys:
            with self.subTest(message_key=message_key):
                hl7_message = parse_message(pharmacy_messages[message_key])

                result = transform_pharmacy_message(hl7_message)

                self.assertIsNone(result, f"Message {message_key} should be dropped (return None)")

    def test_transform_pharmacy_message_preserves_content(self) -> None:
        hl7_message = parse_message(pharmacy_messages["valid_assigning_authority_108"])
        result = transform_pharmacy_message(hl7_message)

        original_msh = hl7_message.msh
        result_msh = result.msh

        self.assertEqual(result_msh.msh_3.value, original_msh.msh_3.value)
        self.assertEqual(result_msh.msh_4.value, original_msh.msh_4.value)
        self.assertEqual(result_msh.msh_5.value, original_msh.msh_5.value)
        self.assertEqual(result_msh.msh_6.value, original_msh.msh_6.value)
        self.assertEqual(result_msh.msh_9.value, original_msh.msh_9.value)
        self.assertEqual(result_msh.msh_10.value, original_msh.msh_10.value)
