"""Tests for RISP sender/version/message-type validation (plan §3a)."""

from __future__ import annotations

import unittest

from hl7apy.parser import parse_message

from hl7_rest_server.custom_validation.risp_validation import validate_risp_message
from hl7_rest_server.exceptions.validation_exception import ValidationException


def _msg(sending_facility: str, message_type: str, version: str = "2.5.1") -> object:
    er7 = (
        f"MSH|^~\\&|{sending_facility}|{sending_facility}|MPI|MPI|20240101120000||{message_type}|MSGID001|P|{version}\r"
        "EVN|A28|20240101120000\r"
        "PID|1||654321^^^NHS||DOE^JANE||19900101|F"
    )
    return parse_message(er7, find_groups=False)


class ValidateRispMessageTests(unittest.TestCase):
    def test_valid_a28_with_correct_facility_and_version(self) -> None:
        validate_risp_message(_msg("349", "ADT^A28^ADT_A05"))  # should not raise

    def test_valid_a31_with_correct_facility_and_version(self) -> None:
        validate_risp_message(_msg("349", "ADT^A31^ADT_A05"))

    def test_valid_a40_with_correct_facility_and_version(self) -> None:
        validate_risp_message(_msg("349", "ADT^A40^ADT_A39"))

    def test_a28_with_wrong_facility_is_rejected(self) -> None:
        with self.assertRaises(ValidationException):
            validate_risp_message(_msg("350", "ADT^A28^ADT_A05"))

    def test_a28_with_wrong_version_is_rejected(self) -> None:
        with self.assertRaises(ValidationException):
            validate_risp_message(_msg("349", "ADT^A28^ADT_A05", version="2.5"))

    def test_oru_r01_within_facility_range_is_valid(self) -> None:
        validate_risp_message(_msg("350", "ORU^R01^ORU_R01"))
        validate_risp_message(_msg("358", "ORU^R01^ORU_R01"))

    def test_omg_o19_within_facility_range_is_valid(self) -> None:
        validate_risp_message(_msg("355", "OMG^O19^OMG_O19"))

    def test_oru_r01_outside_facility_range_is_rejected(self) -> None:
        with self.assertRaises(ValidationException):
            validate_risp_message(_msg("359", "ORU^R01^ORU_R01"))
        with self.assertRaises(ValidationException):
            validate_risp_message(_msg("349", "ORU^R01^ORU_R01"))

    def test_oru_r01_non_numeric_facility_is_rejected(self) -> None:
        with self.assertRaises(ValidationException):
            validate_risp_message(_msg("ABC", "ORU^R01^ORU_R01"))

    def test_unsupported_message_type_is_rejected(self) -> None:
        with self.assertRaises(ValidationException):
            validate_risp_message(_msg("349", "ADT^A01^ADT_A01"))


if __name__ == "__main__":
    unittest.main()
