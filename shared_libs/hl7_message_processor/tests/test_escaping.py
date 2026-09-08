import unittest

from hl7_message_processor.escaping import decode_hl7_escapes, encode_hl7_escapes


class DecodeHl7EscapesTests(unittest.TestCase):
    def test_subcomponent_separator_escape_decodes_to_ampersand(self) -> None:
        self.assertEqual(decode_hl7_escapes(r"BGH ACCIDENT \T\ EMERGENCY"), "BGH ACCIDENT & EMERGENCY")

    def test_all_simple_mnemonic_escapes(self) -> None:
        self.assertEqual(decode_hl7_escapes("\\F\\"), "|")
        self.assertEqual(decode_hl7_escapes("\\S\\"), "^")
        self.assertEqual(decode_hl7_escapes("\\R\\"), "~")
        self.assertEqual(decode_hl7_escapes("\\T\\"), "&")
        self.assertEqual(decode_hl7_escapes("\\E\\"), "\\")

    def test_hex_escapes_for_cr_and_lf(self) -> None:
        self.assertEqual(decode_hl7_escapes("\\X0D\\"), "\r")
        self.assertEqual(decode_hl7_escapes("\\X0A\\"), "\n")

    def test_line_break_escape(self) -> None:
        self.assertEqual(decode_hl7_escapes("line1\\.br\\line2"), "line1\r\nline2")

    def test_unknown_escape_sequence_left_untouched(self) -> None:
        self.assertEqual(decode_hl7_escapes("\\Z\\"), "\\Z\\")

    def test_text_without_backslash_returned_unchanged(self) -> None:
        self.assertEqual(decode_hl7_escapes("plain text"), "plain text")

    def test_empty_string_returned_unchanged(self) -> None:
        self.assertEqual(decode_hl7_escapes(""), "")


class EncodeHl7EscapesTests(unittest.TestCase):
    def test_ampersand_encodes_to_subcomponent_escape(self) -> None:
        self.assertEqual(encode_hl7_escapes("BGH ACCIDENT & EMERGENCY"), "BGH ACCIDENT \\T\\ EMERGENCY")

    def test_all_simple_delimiter_characters(self) -> None:
        self.assertEqual(encode_hl7_escapes("|"), "\\F\\")
        self.assertEqual(encode_hl7_escapes("^"), "\\S\\")
        self.assertEqual(encode_hl7_escapes("~"), "\\R\\")
        self.assertEqual(encode_hl7_escapes("&"), "\\T\\")
        self.assertEqual(encode_hl7_escapes("\\"), "\\E\\")

    def test_carriage_return_and_line_feed(self) -> None:
        self.assertEqual(encode_hl7_escapes("\r"), "\\X0D\\")
        self.assertEqual(encode_hl7_escapes("\n"), "\\X0A\\")
        self.assertEqual(encode_hl7_escapes("\r\n"), "\\X0D\\\\X0A\\")

    def test_empty_string_returned_unchanged(self) -> None:
        self.assertEqual(encode_hl7_escapes(""), "")

    def test_backslash_escaped_before_other_characters_to_avoid_double_escaping(self) -> None:
        # A literal backslash must become \E\ without corrupting the escape sequences
        # subsequently generated for other delimiter characters in the same text.
        self.assertEqual(encode_hl7_escapes("a\\b&c"), "a\\E\\b\\T\\c")


class RoundTripTests(unittest.TestCase):
    def test_decode_then_encode_restores_original_escape_sequences(self) -> None:
        original = "BGH ACCIDENT \\T\\ EMERGENCY"
        self.assertEqual(encode_hl7_escapes(decode_hl7_escapes(original)), original)

    def test_encode_then_decode_restores_original_literal_text(self) -> None:
        original = "BGH ACCIDENT & EMERGENCY"
        self.assertEqual(decode_hl7_escapes(encode_hl7_escapes(original)), original)


if __name__ == "__main__":
    unittest.main()
