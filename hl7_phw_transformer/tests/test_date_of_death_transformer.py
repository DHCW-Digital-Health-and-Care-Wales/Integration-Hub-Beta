import unittest

from hl7_phw_transformer.date_of_death_transformer import transform_date_of_death


class TestDateOfDeathTransformer(unittest.TestCase):
    def test_timezone_is_trimmed_when_length_is_greater_than_6(self) -> None:
        values = [
            ("20250702085450+0000", "20250702085450"),
            ("20241231+0100", "20241231"),
            ("20241231", "20241231"),
        ]

        for original_value, expected_value in values:
            with self.subTest(original_value=original_value):
                self.assertEqual(transform_date_of_death(original_value), expected_value)

    def test_returns_blank_for_empty_or_short_values(self) -> None:
        blank_values = [None, "", "   ", "202401", "123456"]

        for value in blank_values:
            with self.subTest(value=value):
                self.assertEqual(transform_date_of_death(value), '""')


if __name__ == "__main__":
    unittest.main()
