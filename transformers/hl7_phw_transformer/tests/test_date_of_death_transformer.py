import unittest

from hl7_phw_transformer.date_of_death_transformer import transform_date_of_death


class TestDateOfDeathTransformer(unittest.TestCase):
    def test_resurrec_transformation(self) -> None:
        resurrec_variants = [
            "RESURREC",
            "resurrec",
            "Resurrec",
            "  RESURREC  ",
            "\tRESURREC\n"
        ]

        for variant in resurrec_variants:
            with self.subTest(variant=variant):
                self.assertEqual(transform_date_of_death(variant), '""')

    def test_valid_date_passthrough(self) -> None:
        valid_dates = [
            "2023-01-15",
            "1999-12-31",
            "2025-05-23",
            "2000-02-29",  # Leap year date
            "1900-01-01"
        ]

        for date in valid_dates:
            with self.subTest(date=date):
                self.assertEqual(transform_date_of_death(date), date)


if __name__ == "__main__":
    unittest.main()
