import unittest
from pathlib import Path
from dhcw_nhs_wales.inthub.wpas_validator.xmlvalidator import XmlValidator


class TestXmlValidator(unittest.TestCase):
    def setUp(self):
        self.validator = XmlValidator()
        return super().setUp()

    def test_valid_utf16_xml(self):
        xml = self.read_xml("wpas_valid_utf16.xml")

        result = self.validator.validate(xml)

        self.assertTrue(result.is_valid)

    def test_valid_utf8_xml(self):
        xml = self.read_xml("wpas_valid_utf8.xml")

        result = self.validator.validate(xml)

        self.assertTrue(result.is_valid)

    def test_invalid_xml(self):
        xml = self.read_xml("wpas_invalid.xml")

        result = self.validator.validate(xml)

        self.assertFalse(result.is_valid)

    def read_xml(self, filename):
        path = Path(__file__).parent / filename
        xml = ""
        encoding = "utf-16" if "utf16" in filename else "utf-8"
        with open(path, "r", encoding=encoding) as file:
            xml = file.read()
        return xml
