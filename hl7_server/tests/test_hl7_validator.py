import unittest

from hl7apy.parser import parse_message

from hl7_server.hl7_validator import HL7Validator, ValidationException

VALID_A31_MESSAGE = (
    "MSH|^~\\&|192|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.4|||NE|NE\r"
    "EVN|Sub|20250624161510\r"
    "PID|1|1000000001^^^^NH|1000000001^^^^NH~B1000001^^^^PAS||TEST^TEST^^^Mrs.||20000101000000|F|||"
    "1 TEST TEST TEST TEST^TEST^TEST^TEST^CF11 9AD||01000 000001^PRN|01000 000001^WPN||||||||||||||||||1\r"
    "PD1||||G7000001\r"
    "PV1||U\r"
)

VALID_PHW_A28_MESSAGE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|202505052323326666666666|P|2.5|||||GBR||EN\r"
    "EVN||20250502102000|20250505232328|||20250505232328\r"
    "PID|||8888888^^^252^PI~6666666666^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19920809|M|^^||"
    "ADDRESS1^ADDRESS2^ADDRESS3^ADDRESS4^XX99 9XX^^H~^^^^^^||^^^~|||||||||||||||||||01\r"
    "PD1|||^^W99999^|G7777777\r"
    "PV1||\r"
)


class TestHL7Validator(unittest.TestCase):
    def test_no_flow_name_skips_flow_specific_validation(self) -> None:
        msg = parse_message(VALID_A31_MESSAGE)

        validator = HL7Validator(hl7_version="2.4", sending_app="TestApp, 192, 255")

        validator.validate(msg)

    def test_without_validation(self) -> None:
        msg = parse_message(VALID_A31_MESSAGE)
        validator = HL7Validator()

        validator.validate(msg)

    def test_non_phw_flow_skips_phw_validation(self) -> None:
        msg = parse_message(VALID_A31_MESSAGE)

        validator = HL7Validator(hl7_version="2.4", sending_app="TestApp, 192, 255", flow_name="chemo")

        validator.validate(msg)

    def test_invalid_hl7version_raises_exception(self) -> None:
        msg = parse_message(VALID_A31_MESSAGE)
        validator = HL7Validator("2.3", "192")

        with self.assertRaises(ValidationException):
            validator.validate(msg)

    def test_invalid_sending_app_raises_exception(self) -> None:
        msg = parse_message(VALID_A31_MESSAGE)
        validator = HL7Validator("2.4", "101")

        with self.assertRaises(ValidationException):
            validator.validate(msg)

    def test_multiple_sending_apps_valid(self) -> None:
        msg = parse_message(VALID_A31_MESSAGE)
        validator = HL7Validator("2.4", "TestApp, 252, 192")

        validator.validate(msg)

    def test_multiple_sending_apps_none_match_raises_exception(self) -> None:
        msg = parse_message(VALID_A31_MESSAGE)
        validator = HL7Validator("2.4", "TestApp, 199, 255")

        with self.assertRaises(ValidationException):
            validator.validate(msg)
