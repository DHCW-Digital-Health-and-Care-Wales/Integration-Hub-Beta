"""Tests for the message input adapter (ER7 passthrough and XML → ER7)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from rest_server.hl7 import message_input_adapter
from rest_server.hl7.message_input_adapter import to_er7


class ToEr7Tests(unittest.TestCase):
    def test_er7_passthrough_normalises_crlf(self) -> None:
        content = "MSH|^~\\&|A|B\r\nPID|1"
        result = to_er7(content)
        self.assertEqual(result, "MSH|^~\\&|A|B\rPID|1")

    def test_er7_passthrough_normalises_lf(self) -> None:
        content = "MSH|^~\\&|A|B\nPID|1"
        result = to_er7(content)
        self.assertEqual(result, "MSH|^~\\&|A|B\rPID|1")

    def test_er7_already_cr_is_unchanged(self) -> None:
        content = "MSH|^~\\&|A|B\rPID|1"
        self.assertEqual(to_er7(content), content)

    def test_xml_content_is_delegated_to_converter(self) -> None:
        xml = "<ADT_A28 xmlns=\"urn:hl7-org:v2xml\"><MSH/></ADT_A28>"
        with patch.object(message_input_adapter, "xml_to_er7", return_value="MSH|^~\\&|A") as mock_convert:
            result = to_er7(xml)
        mock_convert.assert_called_once_with(xml)
        self.assertEqual(result, "MSH|^~\\&|A")

    def test_xml_with_leading_whitespace_is_detected(self) -> None:
        xml = "   \n<ADT_A28/>"
        with patch.object(message_input_adapter, "xml_to_er7", return_value="MSH|X") as mock_convert:
            to_er7(xml)
        mock_convert.assert_called_once()

    def test_empty_content_is_treated_as_er7(self) -> None:
        with patch.object(message_input_adapter, "xml_to_er7") as mock_convert:
            result = to_er7("")
        mock_convert.assert_not_called()
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
