import unittest

from hl7_validation import validate_er7_with_flow
from hl7_validation.validate import XmlValidationError


class TestParisValidation(unittest.TestCase):
    def test_paris_a05_schema_validation_working(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|169|169|100|100|20250619115001||ADT^A28^ADT_A05|185352620250619115001|P|2.5.1|||||GBR||EN",
            "EVN||20250619115001||||20250619115001",
            "PID|||700001^^^169^PI||TEST^Patient^^^^^U||20000101|M|||1 TEST STREET^^^TEST^CF11 9AD||~900001|||||||||Z",
            "PV1||N"
        ])

        validate_er7_with_flow(er7, "paris")

    def test_paris_a39_schema_validation_working(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|169|169|100|100|20250618154752||ADT^A40^ADT_A39|185270320250618154752|P|2.5.1|||||GBR||EN",
            "EVN||||||20250618154752",
            "PID|||7000000001^^^NHS^NH~700002^^^169^PI",
            "MRG|700001^^^169^PI"
        ])

        validate_er7_with_flow(er7, "paris")

    def test_paris_a28_incorrectly_structured_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|169|169|100|100|20250619115001||ADT^A28^ADT_A05|185352620250619115001|P|2.5.1|||||GBR||EN",
            "EVN||20250619115001||||20250619115001",
            "XXX|This is an invalid segment not in the schema",
            "PID|||700001^^^169^PI||TEST^Patient^^^^^U||20000101|M|||1 TEST STREET^^^TEST^CF11 9AD||~900001|||||||||Z",
            "PV1||N"
        ])

        with self.assertRaises(XmlValidationError):
            validate_er7_with_flow(er7, "paris")

    def test_paris_a28_correctly_structured_invalid_data_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|169|169|100|100|20250619115001||ADT^A28^ADT_A05|185352620250619115001|P|2.5.1|||||GBR||EN",
            "EVN||20250619115001||||20250619115001",
            "PID|||700001^^^169^PI||TEST^Patient^^^^^U||20000101|M|||1 TEST STREET^^^TEST^CF11 9AD||~900001|||||||||Z"
        ])

        with self.assertRaises(XmlValidationError):
            validate_er7_with_flow(er7, "paris")
