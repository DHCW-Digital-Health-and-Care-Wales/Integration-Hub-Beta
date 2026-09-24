import os
import tempfile
import unittest
from typing import Any
from unittest import mock

from hl7apy.consts import VALIDATION_LEVEL

from hl7_message_processor.exceptions import Hl7MessageValidationError
from hl7_message_processor.validator import validate_hl7_message

VALID_ADT_A05 = (
    "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A28^ADT_A05|MSG00001|P|2.5.1\r"
    "EVN|A28|20241230133601\r"
    "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
    "PV1|1|I"
)

MISSING_SEGMENTS_ADT_A05 = (
    "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A28^ADT_A05|MSG00001|P|2.5.1\r"
    "PID|1\r"
    "PD1|||^^W99999|G9999999"
)

INVALID_NM_VALUE_MESSAGE = (
    "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20240331074526||ADT^A28^ADT_A05|1272212201|P|2.5.1\r"
    "PD1|||^^W99999|G9999999"
)

VALID_ADT_A05_WITH_TABLE_WARNING = (
    "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A28^ADT_A05|MSG00001|P|2.5.1\r"
    "EVN|A28|20241230133601\r"
    "PID|1||123456^^^MRN^MR||DOE^JOHN||||||^^^^^^HOME\r"
    "PV1|1|I"
)


class ValidateHl7MessageStrictTests(unittest.TestCase):
    def test_invalid_nm_value_raises_single_error(self) -> None:
        with self.assertRaises(Hl7MessageValidationError) as ctx:
            validate_hl7_message(INVALID_NM_VALUE_MESSAGE, validation_level=VALIDATION_LEVEL.STRICT)

        self.assertIn("W99999 is not an HL7 valid NM value", str(ctx.exception))

    def test_valid_message_passes(self) -> None:
        with self.assertLogs("hl7_message_processor.validator", level="INFO") as logs:
            validate_hl7_message(VALID_ADT_A05, validation_level=VALIDATION_LEVEL.STRICT)

        self.assertTrue(any("passed hl7apy validation" in message for message in logs.output))


class ValidateHl7MessageTolerantTests(unittest.TestCase):
    def test_missing_required_segments_reports_all_errors(self) -> None:
        with self.assertRaises(Hl7MessageValidationError) as ctx:
            validate_hl7_message(MISSING_SEGMENTS_ADT_A05, validation_level=VALIDATION_LEVEL.TOLERANT)

        message = str(ctx.exception)
        self.assertIn("Missing required child ADT_A05.EVN", message)
        self.assertIn("Missing required child ADT_A05.PV1", message)

    def test_errors_are_logged_individually(self) -> None:
        with self.assertLogs("hl7_message_processor.validator", level="ERROR") as logs:
            with self.assertRaises(Hl7MessageValidationError):
                validate_hl7_message(MISSING_SEGMENTS_ADT_A05, validation_level=VALIDATION_LEVEL.TOLERANT)

        joined = "\n".join(logs.output)
        self.assertIn("Missing required child ADT_A05.EVN", joined)
        self.assertIn("Missing required child ADT_A05.PV1", joined)

    def test_valid_message_passes_and_logs_success(self) -> None:
        with self.assertLogs("hl7_message_processor.validator", level="INFO") as logs:
            validate_hl7_message(VALID_ADT_A05, validation_level=VALIDATION_LEVEL.TOLERANT)

        self.assertTrue(any("passed hl7apy validation" in message for message in logs.output))

    def test_default_validation_level_is_tolerant(self) -> None:
        # MISSING_SEGMENTS_ADT_A05 would fail with a bare ValueError before the report-file pass if
        # parsed STRICT (unrelated field), so use a message that would only fail cardinality checks
        # to prove the *default* level is TOLERANT (parses successfully either way here).
        with self.assertRaises(Hl7MessageValidationError):
            validate_hl7_message(MISSING_SEGMENTS_ADT_A05)

    def test_on_warning_callback_receives_raw_warning_text(self) -> None:
        received: list[str] = []

        validate_hl7_message(
            VALID_ADT_A05_WITH_TABLE_WARNING,
            validation_level=VALIDATION_LEVEL.TOLERANT,
            on_warning=received.append,
        )

        self.assertEqual(len(received), 1)
        self.assertIn("HOME", received[0])
        self.assertIn("HL70190", received[0])

    def test_on_warning_callback_not_called_when_no_warnings(self) -> None:
        received: list[str] = []

        validate_hl7_message(
            VALID_ADT_A05,
            validation_level=VALIDATION_LEVEL.TOLERANT,
            on_warning=received.append,
        )

        self.assertEqual(received, [])

    def test_on_warning_callback_is_optional(self) -> None:
        # Must not raise even though the message produces a warning and no callback is supplied.
        validate_hl7_message(VALID_ADT_A05_WITH_TABLE_WARNING, validation_level=VALIDATION_LEVEL.TOLERANT)


class ValidateHl7MessageReportFileCleanupTests(unittest.TestCase):
    def test_temp_report_file_is_removed_after_call(self) -> None:
        created_paths = []
        original_mkstemp = tempfile.mkstemp

        def _tracking_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
            fd, path = original_mkstemp(*args, **kwargs)
            created_paths.append(path)
            return fd, path

        with mock.patch("hl7_message_processor.validator.tempfile.mkstemp", side_effect=_tracking_mkstemp):
            validate_hl7_message(VALID_ADT_A05, validation_level=VALIDATION_LEVEL.TOLERANT)

        self.assertEqual(len(created_paths), 1)
        self.assertFalse(os.path.exists(created_paths[0]))


if __name__ == "__main__":
    unittest.main()
