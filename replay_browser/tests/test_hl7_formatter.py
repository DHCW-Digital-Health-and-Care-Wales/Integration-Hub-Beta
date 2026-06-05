import unittest

from replay_browser.hl7_formatter import first_field_value, parse_hl7


class TestHl7Formatter(unittest.TestCase):
    def test_parse_hl7_extracts_segments_and_fields(self) -> None:
        hl7 = (
            "MSH|^~\\&|252|252|100|100|20250505232332||ADT^A31^ADT_A05|CTRL-1|P|2.5\r"
            "EVN|A31|20250505232332\r"
            "PID|||9999999^^^NHS^NH||DOE^JOHN"
        )

        segments = parse_hl7(hl7)

        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].name, "MSH")
        self.assertEqual(first_field_value(segments, "MSH", 9), "ADT^A31^ADT_A05")
        self.assertEqual(first_field_value(segments, "MSH", 10), "CTRL-1")
        self.assertEqual(first_field_value(segments, "EVN", 1), "A31")

    def test_parse_hl7_parses_repetitions_components_and_subcomponents(self) -> None:
        hl7 = "OBX|1|TX|CODE^DESC|1|A^B&C~X^Y\r"

        segments = parse_hl7(hl7)
        field = segments[0].fields[4]

        self.assertEqual(field.number, 5)
        self.assertEqual(len(field.repetitions), 2)
        self.assertEqual(field.repetitions[0].components[1].subcomponents[1].value, "C")

    def test_parse_hl7_empty_text_returns_no_segments(self) -> None:
        self.assertEqual(parse_hl7("   \n\r"), [])


if __name__ == "__main__":
    unittest.main()
