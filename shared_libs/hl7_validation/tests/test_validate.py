import unittest

from hl7_validation.convert import er7_to_xml
from hl7_validation.validate import (
    validate_xml,
    validate_xml_with_schema,
    XmlValidationError,
)
from hl7_validation import get_schema_xsd_path


class TestValidate(unittest.TestCase):
    def test_validate_xml_minimal_schema(self) -> None:
        er7 = "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A28|MSGID|P|2.5\rPID|1||12345^^^HOSP^MR||Doe^John||19800101|M\r"
        xml_str = er7_to_xml(er7)
        xsd_path = get_schema_xsd_path("phw_schema")
        validate_xml(xml_str, xsd_path)

    def test_validate_xml_raises_on_error(self) -> None:
        bad_xml = "<HL7Message><MSH></MSH></HL7Message>"
        xsd_path = get_schema_xsd_path("phw_schema")
        with self.assertRaises(XmlValidationError):
            validate_xml(bad_xml, xsd_path)

    def test_validate_xml_with_schema_helper(self) -> None:
        er7 = "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A28|MSGID|P|2.5\rPID|1||12345^^^HOSP^MR||Doe^John||19800101|M\r"
        xml_str = er7_to_xml(er7)
        # Should not raise
        validate_xml_with_schema(xml_str, "phw_schema")


if __name__ == "__main__":
    unittest.main()


