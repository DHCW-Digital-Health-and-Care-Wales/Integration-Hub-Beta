import os
import unittest

from hl7_validation.convert import er7_to_xml
from hl7_validation.validate import validate_xml, XmlValidationError


class TestValidate(unittest.TestCase):
    def test_validate_xml_minimal_schema(self) -> None:
        er7 = "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A28|MSGID|P|2.5\rPID|1||12345^^^HOSP^MR||Doe^John||19800101|M\r"
        xml_str = er7_to_xml(er7)
        xsd_path = os.path.join(os.path.dirname(__file__), "..", "hl7_validation", "resources", "hl7v2_5_minimal.xsd")
        xsd_path = os.path.abspath(xsd_path)
        validate_xml(xml_str, xsd_path)

    def test_validate_xml_raises_on_error(self) -> None:
        bad_xml = "<HL7Message><MSH></MSH></HL7Message>"  # missing required fields
        xsd_path = os.path.join(os.path.dirname(__file__), "..", "hl7_validation", "resources", "hl7v2_5_minimal.xsd")
        xsd_path = os.path.abspath(xsd_path)
        with self.assertRaises(XmlValidationError):
            validate_xml(bad_xml, xsd_path)


if __name__ == "__main__":
    unittest.main()


