import unittest

from hl7_validation import validate_er7_with_flow_schema
from hl7_validation.validate import XmlValidationError


class TestChemoMessages(unittest.TestCase):
    def test_chemo_a31_schema_validation_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|212|212|200|200|20250701140735||ADT^A31|201600952808665|P|2.4|||NE|"
            "NE EVN|Sub|20250701140735",
            "PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^T^^Mrs.||20000101000000|F|||"
            "TEST,^TEST^TEST TEST^^CF11 9AD||01000 000 001|07000000001||||||||||||||||||0",
            "PD1||||G7000001",
            "PV1||U"
        ])

        validate_er7_with_flow_schema(er7, "chemo")

    def test_chemo_a28_schema_validation_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|212|212|200|200|20250701153930||ADT^A28|547417054344058|P|2.4|||NE|NE",
            "EVN|Sub|20250701153930",
            "PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^^^Mr.||20000101000000|M|||"
            "1, TEST^TEST^TEST^^CF11 9AD||01000 000001|||||||||||||||||||0",
            "PD1||||G0000001",
            "PV1||U"
        ])

        validate_er7_with_flow_schema(er7, "chemo")

    def test_chemo_a31_incorrectly_structured_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|212|212|200|200|20250701140735||ADT^A31|201600952808665|P|2.4|||NE|"
            "NE EVN|Sub|20250701140735",
            "XXX|This is an invalid segment not in the schema",  # Invalid segment
            "PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^T^^Mrs.||20000101000000|F|||"
            "TEST,^TEST^TEST TEST^^CF11 9AD||01000 000 001|07000000001||||||||||||||||||0",
            "PD1||||G7000001",
            "PV1||U"
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "chemo")
        error_message = str(context.exception)
        self.assertIn("Unable to parse ER7 message", error_message)

    def test_chemo_a31_correctly_structured_invalid_data_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|212|212|200|200|20250701140735||ADT^A31|201600952808665|P|2.4|||NE|"
            "NE EVN|Sub|20250701140735",
            "PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^T^^Mrs.||20000101000000|F|||"
            "TEST,^TEST^TEST TEST^^CF11 9AD||01000 000 001|07000000001||||||||||||||||||0",
            "PD1||||G7000001"
            # Missing PV1 segment which is required according to ADT_A31 schema
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "chemo")
        error_message = str(context.exception)
        self.assertIn("PV1' expected", error_message)

    def test_chemo_a40_schema_validation_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|212|212|200|200|20250701140735||ADT^A40|201600952808665|P|2.4|||NE|NE",
            "EVN|Sub|20250701140735",
            "PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^T^^Mrs.||20000101000000|F|||"
            "TEST,^TEST^TEST TEST^^CF11 9AD||01000 000 001|07000000001||||||||||||||||||0",
            "PD1||||G7000021",
            "MRG|346534",
            "PV1||U",
        ])

        validate_er7_with_flow_schema(er7, "chemo")

    def test_chemo_a40_with_nk1_schema_validation_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|212|212|200|200|20250701140735||ADT^A40|201600952808665|P|2.4|||NE|NE",
            "EVN|Sub|20250701140735",
            "PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^T^^Mrs.||20000101000000|F|||"
            "TEST,^TEST^TEST TEST^^CF11 9AD||01000 000 001|07000000001||||||||||||||||||0",
            "PD1||||G7000021",
            "NK1|1|JONES^BARBARA^K|WIFE||||||NK^NEXT OF KIN",
            "MRG|346534",
            "PV1||U",
        ])

        validate_er7_with_flow_schema(er7, "chemo")

    def test_chemo_a40_without_optional_segments_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|245|245|100|100|20250701141950||ADT^A40|596887414401487|P|2.4|||NE|NE",
            "EVN||20250701141950",
            "PID|1|1000000001^^^^NH|1000000001^^^^NH~00rb00^^^^PI||TEST^TEST||20000101000000|M|||"
            "1 Street^Town^Rhondda, cynon, taff^^CF11 9AD||07000000001",
            "MRG|745001^^^245^PI",
        ])

        validate_er7_with_flow_schema(er7, "chemo")

    def test_chemo_a40_missing_mrg_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|212|212|200|200|20250701140735||ADT^A40|201600952808665|P|2.4|||NE|NE",
            "EVN|Sub|20250701140735",
            "PID|1|1000000001^^^^NH|1000000001^^^^NH||TEST^TEST^T^^Mrs.||20000101000000|F|||"
            "TEST,^TEST^TEST TEST^^CF11 9AD||01000 000 001|07000000001||||||||||||||||||0",
            "PV1||U",
            # Missing MRG segment which is required for A40 messages per ADT_A39 schema
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "chemo")
        error_message = str(context.exception)
        self.assertIn("MRG", error_message)
