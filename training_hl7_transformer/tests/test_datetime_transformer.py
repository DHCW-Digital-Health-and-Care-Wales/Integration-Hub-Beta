import unittest

from training_hl7_transformer.datetime_transformer import transform_datetime_to_hl7, transform_datetime_to_readable


class TestDateTimeTransformer(unittest.TestCase):

    def setUp(self) -> None:
        self.valid_hl7_datetime = "20260122143055"
        self.valid_readable_datetime = "2026-01-22 14:30:55"
        self.invalid_datetime = "2026-01-22T14:30:55"  # Incorrect format


    def test_transform_datetime_to_readable_valid(self) -> None:

        result = transform_datetime_to_readable(self.valid_hl7_datetime)

        self.assertEqual(result, self.valid_readable_datetime)


    def test_transform_datetime_to_readable_invalid(self) -> None:

        with self.assertRaises(ValueError):
            transform_datetime_to_readable(self.invalid_datetime)


    def test_transform_datetime_to_hl7_valid(self) -> None:

        result = transform_datetime_to_hl7(self.valid_readable_datetime)

        self.assertEqual(result, self.valid_hl7_datetime)
