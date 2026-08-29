import unittest

from ultra7.formats.pretty_print import pretty_print


class TestPrettyPrintJson(unittest.TestCase):
    def test_indents_compact_json(self) -> None:
        result = pretty_print('{"a":1,"b":[1,2,3]}', "json")
        self.assertEqual(result, '{\n  "a": 1,\n  "b": [\n    1,\n    2,\n    3\n  ]\n}')

    def test_invalid_json_raises(self) -> None:
        with self.assertRaises(ValueError):
            pretty_print("{not valid", "json")


class TestPrettyPrintXml(unittest.TestCase):
    def test_indents_compact_xml(self) -> None:
        result = pretty_print("<root><child>value</child></root>", "xml")
        self.assertIn("<root>", result)
        self.assertIn("  <child>value</child>", result)
        self.assertTrue(result.count("\n") >= 2)

    def test_invalid_xml_raises(self) -> None:
        with self.assertRaises(ValueError):
            pretty_print("<root><unclosed>", "xml")


class TestPrettyPrintUnsupportedFormat(unittest.TestCase):
    def test_hl7_is_unsupported(self) -> None:
        with self.assertRaises(ValueError):
            pretty_print("MSH|^~\\&|...", "hl7")


if __name__ == "__main__":
    unittest.main()
