import unittest

from hl7_phw_transformer.datetime_transformer import transform_datetime


class TestDatetimeTransformer(unittest.TestCase):
    def test_valid_date(self) -> None:
        self.assertEqual(transform_datetime("2023-01-15 09:45:30"), "20230115094530")
        self.assertEqual(transform_datetime("1999-12-31 23:59:59"), "19991231235959")
        self.assertEqual(transform_datetime("2025-05-23 00:00:00"), "20250523000000")

    def test_already_formatted_date(self) -> None:
        self.assertEqual(transform_datetime("20230115094530"), "20230115094530")
        self.assertEqual(transform_datetime("19991231235959"), "19991231235959")
        self.assertEqual(transform_datetime("20250523000000"), "20250523000000")

    def test_invalid_format(self) -> None:
        with self.assertRaises(ValueError):
            transform_datetime("2023/01/15 09:45:30")
        with self.assertRaises(ValueError):
            transform_datetime("15-01-2023_09:45:30")
        with self.assertRaises(ValueError):
            transform_datetime("2023-01-15T09:45:30")
        with self.assertRaises(ValueError):
            transform_datetime("2023A115094530")
        with self.assertRaises(ValueError):
            transform_datetime("2023-01-15_09:45:30")

    def test_empty_string(self) -> None:
        with self.assertRaises(ValueError):
            transform_datetime("")

    def test_incorrect_datetime(self) -> None:
        with self.assertRaises(ValueError):
            transform_datetime("2023-02-30 12:00:00")  # Invalid date


if __name__ == "__main__":
    unittest.main()
