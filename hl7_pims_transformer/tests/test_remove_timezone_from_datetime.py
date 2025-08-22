import unittest

from hl7_pims_transformer.utils.remove_timezone_from_datetime import remove_timezone_from_datetime


class TestRemoveTimezoneFromDatetime(unittest.TestCase):

    def test_remove_timezone_full_datetime_production_format(self) -> None:
        result = remove_timezone_from_datetime("20250819115447+0000")
        self.assertEqual(result, "20250819115447")

    def test_remove_timezone_date_only_format(self) -> None:
        result = remove_timezone_from_datetime("20000101+")
        self.assertEqual(result, "20000101")

        result = remove_timezone_from_datetime("20000101+0000")
        self.assertEqual(result, "20000101")

    def test_remove_timezone_various_formats(self) -> None:
        """Test various timezone format patterns found in production."""
        test_cases = [
            # Full datetime formats
            ("20250819115447+0000", "20250819115447"),  # GMT
            ("20250819115447+0100", "20250819115447"),  # Positive offset

            # Date-only formats
            ("20000101+", "20000101"),                  # Date with timezone indicator
            ("20000101+0000", "20000101"),              # Date with GMT
            ("19990630+0100", "19990630"),              # Date with positive offset
        ]

        for input_datetime, expected_output in test_cases:
            with self.subTest(input_datetime=input_datetime):
                result = remove_timezone_from_datetime(input_datetime)
                self.assertEqual(result, expected_output)

    def test_datetime_without_timezone_unchanged(self) -> None:
        # Full datetime without timezone
        result = remove_timezone_from_datetime("20250819115447")
        self.assertEqual(result, "20250819115447")

        # Date without timezone
        result = remove_timezone_from_datetime("20000101")
        self.assertEqual(result, "20000101")

    def test_invalid_length_after_timezone_removal(self) -> None:
        invalid_length_cases = [
            "2025081+0000",         # 7 characters - too short for date
            "200508191+0000",       # 9 characters - between date and datetime
            "202508191154470+0000", # 15 characters - too long for datetime
            "20250819115447-0100"   # with negative timezone offset
        ]

        for input_value in invalid_length_cases:
            with self.subTest(input_value=input_value):
                with self.assertRaises(ValueError) as context:
                    remove_timezone_from_datetime(input_value)
                self.assertIn("Invalid datetime format after timezone removal", str(context.exception))
                self.assertIn("Expected format: YYYYMMDD (8 digits) or YYYYMMDDHHMMSS (14 digits)",
                             str(context.exception))

    def test_invalid_format_non_numeric_characters(self) -> None:
        invalid_format_cases = [
            "2025081a+0000",       # Invalid date format with letter
            "20250819115a47+0000", # Invalid datetime format with letter
            "2025-08-19+0000",     # Date with hyphens
            "2025/08/19+0000",     # Date with slashes
        ]

        for input_value in invalid_format_cases:
            with self.subTest(input_value=input_value):
                with self.assertRaises(ValueError) as context:
                    remove_timezone_from_datetime(input_value)
                self.assertIn("Invalid datetime format after timezone removal", str(context.exception))
