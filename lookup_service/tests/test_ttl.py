from __future__ import annotations

import unittest

from lookup_service.errors import InvalidSettingsError
from lookup_service.ttl import format_ttl, split_ttl, ttl_to_seconds


class TtlTests(unittest.TestCase):
    def test_conversion(self) -> None:
        self.assertEqual(ttl_to_seconds(90, "seconds"), 90)
        self.assertEqual(ttl_to_seconds(2, "minutes"), 120)
        self.assertEqual(ttl_to_seconds(3, "hours"), 10800)
        self.assertEqual(ttl_to_seconds(7, "days"), 604800)

    def test_rejects_out_of_range_and_unknown_unit(self) -> None:
        for value, unit in ((0, "seconds"), (-1, "hours"), (8, "days"), (10081, "minutes"), (1, "weeks")):
            with self.subTest(value=value, unit=unit), self.assertRaises(InvalidSettingsError):
                ttl_to_seconds(value, unit)

    def test_split_picks_largest_exact_unit(self) -> None:
        self.assertEqual(split_ttl(86400), (1, "days"))
        self.assertEqual(split_ttl(7200), (2, "hours"))
        self.assertEqual(split_ttl(90), (90, "seconds"))
        self.assertEqual(split_ttl(300), (5, "minutes"))

    def test_format(self) -> None:
        self.assertEqual(format_ttl(1), "1 second")
        self.assertEqual(format_ttl(300), "5 minutes")
        self.assertEqual(format_ttl(86400), "1 day")
