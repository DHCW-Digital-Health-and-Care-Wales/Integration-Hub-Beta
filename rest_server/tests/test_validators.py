import tempfile
import unittest
from pathlib import Path

from hl7_validation import convert_er7_to_xml_with_flow_schema

from rest_server.errors import ValidationError
from rest_server.validators.hl7_xsd_validator import Hl7XsdValidator
from rest_server.validators.no_op_validator import NoOpValidator
from rest_server.validators.xsd_validator import XsdValidator

VALID_ER7_A05 = "\r".join(
    [
        "MSH|^~\\&|328|328|100|100|2026-07-29 09:50:37||ADT^A28^ADT_A05|6778031837018553261z82215|P|2.5|||||GBR||EN",
        "EVN|A28|20260729095037|20260729095037|||20260729095037",
        "PID|||B0000010612^^^328^PI||LIMS^TEST",
        "PV1||",
    ]
)

MINIMAL_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Document">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="Body" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


class TestNoOpValidator(unittest.TestCase):
    def test_validate_never_raises(self) -> None:
        NoOpValidator().validate("<anything/>", None)


class TestHl7XsdValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_payload_xml = convert_er7_to_xml_with_flow_schema(VALID_ER7_A05, "phw")

    def test_valid_payload_passes(self) -> None:
        validator = Hl7XsdValidator(schema_group="phw", allowed_structures={"ADT_A05", "ADT_A39"})
        validator.validate(self.valid_payload_xml, "ADT_A05")

    def test_disallowed_structure_raises(self) -> None:
        validator = Hl7XsdValidator(schema_group="phw", allowed_structures={"ADT_A39"})
        with self.assertRaises(ValidationError):
            validator.validate(self.valid_payload_xml, "ADT_A05")

    def test_missing_structure_id_raises(self) -> None:
        validator = Hl7XsdValidator(schema_group="phw", allowed_structures={"ADT_A05"})
        with self.assertRaises(ValidationError):
            validator.validate(self.valid_payload_xml, None)

    def test_broken_payload_fails_schema_validation(self) -> None:
        broken_xml = self.valid_payload_xml.replace("<ns0:PID>", "<ns0:PIDX>").replace("</ns0:PID>", "</ns0:PIDX>")
        validator = Hl7XsdValidator(schema_group="phw", allowed_structures={"ADT_A05"})
        with self.assertRaises(ValidationError):
            validator.validate(broken_xml, "ADT_A05")


class TestXsdValidator(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        schema_path = Path(self._tmp_dir.name) / "document.xsd"
        schema_path.write_text(MINIMAL_XSD)
        self.validator = XsdValidator(schema_path=str(schema_path))

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_valid_payload_passes(self) -> None:
        self.validator.validate("<Document><Body>content</Body></Document>", "Document")

    def test_invalid_payload_raises(self) -> None:
        with self.assertRaises(ValidationError):
            self.validator.validate("<Document><Wrong>content</Wrong></Document>", "Document")

    def test_missing_schema_file_raises(self) -> None:
        validator = XsdValidator(schema_path="/does/not/exist.xsd")
        with self.assertRaises(ValidationError):
            validator.validate("<Document><Body>content</Body></Document>", "Document")


if __name__ == "__main__":
    unittest.main()
