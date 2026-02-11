import unittest

from hl7_validation import validate_er7_with_flow_schema
from hl7_validation.validate import XmlValidationError


class TestPPimsValidation(unittest.TestCase):
    def test_pims_a40_convert_and_validate(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|PIMS|BroMor HL7Sender|CPI|BroMor|20250630155035+0000||ADT^A40^ADT_A39|73711860|P|2.3.1",
                "EVN||20250630155034+0000||||20250630155034+0000",
                "PID|||1000000001^01^^^NI~T100001^^^^PI||TEST^TEST^TEST^^MS.||20000101+^D|F|||"
                "1, TEST^TEST TEST^TEST^TEST^CF11 9AD||07000000001 TEST PTNR^PRN^PH~07000000001 PT^ORN^CP|"
                "50500 02920^WPN^PH||S^NONE||||||0|||||||^D||||20250630155034+0000",
                "PD1||||G1000001~W10001",
                "MRG|00100001",
            ]
        )

        validate_er7_with_flow_schema(er7, "pims")

    def test_pims_a04_convert_and_validate(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20250702085450+0000||ADT^A04^ADT_A01|73726643|P|2.3.1",
                "EVN||20250702085440+0000||||20250702085440+0000",
                "PID|||1000000001^03^^^NI~N1000001^^^^PI||TEST^TEST-TEST^\"\"^^MISS||20000101+^D|F|||"
                "1 TEST^TEST^TEST^\"\"^CF11 9AD||07000000001^PRN^PH~07000000001^ORN^CP|07000000001^WPN^PH||"
                "S|||||||||||||^D||||20250702085440+0000",
                "PD1||||G7000001~W90001",
                "PV1||NA"
            ]
        )

        validate_er7_with_flow_schema(er7, "pims")

    def test_pims_a08_convert_and_validate(self) -> None:
        er7 = "\r".join(
            [
                "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20241231101053+0000||ADT^A08^ADT_A01|48209024|P|2.3.1",
                "EVN||20241231101035+0000||||20241231101035+0000",
                "PID|||^03^^^NI~N5022039^^^^PI||TESTER^TEST^\"\"^^MRS.||20000101+^D|F|||"
                "MORRISTON HOSPITAL^HEOL MAES EGLWYS^CWMRHYDYCEIRW^SWANSEASWANSEA^SA6 6NL||"
                "01234567892^PRN^PH~01234567896^ORN^CP|^WPN^PH||M||||||1|||||||^D||||20241231101035+0000",
                "PD1||||G9310201~W98006",
                "PV1||NA"
            ]
        )

        validate_er7_with_flow_schema(er7, "pims")

    def test_pims_a40_missing_required_mrg_segment_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|PIMS|BroMor HL7Sender|CPI|BroMor|20250630155035+0000||ADT^A40^ADT_A39|73711860|P|2.3.1",
            "EVN||20250630155034+0000||||20250630155034+0000",
            "PID|||1000000001^01^^^NI~T100001^^^^PI||TEST^TEST^TEST^^MS.||20000101+^D|F|||"
            "1, TEST^TEST TEST^TEST^TEST^CF11 9AD||07000000001 TEST PTNR^PRN^PH~07000000001 PT^ORN^CP|"
            "50500 02920^WPN^PH||S^NONE||||||0|||||||^D||||20250630155034+0000",
            "PD1||||G1000001~W10001"
            # Missing MRG segment which is required for A40 messages per ADT_A39 schema
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "pims")
        error_message = str(context.exception)
        self.assertIn("Tag '{urn:hl7-org:v2xml}MRG' expected", error_message)

    def test_pims_a04_missing_required_pv1_segment_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20250702085450+0000||ADT^A04^ADT_A01|73726643|P|2.3.1",
            "EVN||20250702085440+0000||||20250702085440+0000",
            "PID|||1000000001^03^^^NI~N1000001^^^^PI||TEST^TEST-TEST^\"\"^^MISS||20000101+^D|F|||"
            "1 TEST^TEST^TEST^\"\"^CF11 9AD||07000000001^PRN^PH~07000000001^ORN^CP|07000000001^WPN^PH||"
            "S|||||||||||||^D||||20250702085440+0000",
            "PD1||||G7000001~W90001"
            # Missing PV1 segment which is required for A04 messages per ADT_A01 schema
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "pims")
        error_message = str(context.exception)
        self.assertIn("Tag '{urn:hl7-org:v2xml}PV1' expected", error_message)

    def test_pims_a40_missing_required_pid_segment_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|PIMS|BroMor HL7Sender|CPI|BroMor|20250630155035+0000||ADT^A40^ADT_A39|73711860|P|2.3.1",
            "EVN||20250630155034+0000||||20250630155034+0000",
            # Missing PID segment which is required per ADT_A39 schema
            "PD1||||G1000001~W10001",
            "MRG|00100001"
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "pims")
        error_message = str(context.exception)
        self.assertIn("Tag '{urn:hl7-org:v2xml}ADT_A39.PIDPD1MRGPV1' expected", error_message)

    def test_pims_a04_missing_required_pid_segment_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20250702085450+0000||ADT^A04^ADT_A01|73726643|P|2.3.1",
            "EVN||20250702085440+0000||||20250702085440+0000",
            # Missing PID segment which is required per ADT_A01 schema
            "PD1||||G7000001~W90001",
            "PV1||NA"
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "pims")
        error_message = str(context.exception)
        self.assertIn("Tag '{urn:hl7-org:v2xml}PID' expected", error_message)

    def test_pims_invalid_segment_type_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|PIMS|BroMor HL7Sender|CPI|BroMor|20250630155035+0000||ADT^A40^ADT_A39|73711860|P|2.3.1",
            "EVN||20250630155034+0000||||20250630155034+0000",
            "XXX|This is an invalid segment not in the HL7 specification",  # Invalid segment type
            "PID|||1000000001^01^^^NI~T100001^^^^PI||TEST^TEST^TEST^^MS.||20000101+^D|F",
            "PD1||||G1000001~W10001",
            "MRG|00100001"
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "pims")
        error_message = str(context.exception)
        self.assertIn("Unable to parse ER7 message", error_message)
