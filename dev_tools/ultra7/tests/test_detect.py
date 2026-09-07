import unittest

from ultra7.formats.detect import detect_format


class TestDetectFormat(unittest.TestCase):
    def test_detects_json_object(self) -> None:
        self.assertEqual(detect_format('{"a": 1}'), "json")

    def test_detects_json_array(self) -> None:
        self.assertEqual(detect_format("[1, 2, 3]"), "json")

    def test_detects_xml(self) -> None:
        self.assertEqual(detect_format("<root><child/></root>"), "xml")

    def test_detects_xml_with_declaration(self) -> None:
        self.assertEqual(detect_format('<?xml version="1.0"?><root/>'), "xml")

    def test_falls_back_to_hl7(self) -> None:
        content = "MSH|^~\\&|SENDAPP|SENDFAC|RECVAPP|RECVFAC|20250703120000||ADT^A01|MSG1|P|2.5"
        self.assertEqual(detect_format(content), "hl7")

    def test_empty_input_defaults_to_hl7(self) -> None:
        self.assertEqual(detect_format(""), "hl7")
        self.assertEqual(detect_format("   "), "hl7")

    def test_malformed_json_falls_back(self) -> None:
        self.assertEqual(detect_format("{not valid json"), "hl7")

    def test_malformed_xml_falls_back(self) -> None:
        self.assertEqual(detect_format("<root><unclosed>"), "hl7")


if __name__ == "__main__":
    unittest.main()
