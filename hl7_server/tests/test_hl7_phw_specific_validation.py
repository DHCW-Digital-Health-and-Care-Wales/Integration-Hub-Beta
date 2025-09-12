import unittest

from hl7apy.parser import parse_message

from hl7_server.hl7_validator import HL7Validator, ValidationException

VALID_PHW_A28_MESSAGE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|202505052323326666666666|P|2.5|||||GBR||EN\r"
    "EVN||20250502102000|20250505232328|||20250505232328\r"
    "PID|||8888888^^^252^PI~6666666666^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||{birthdate}|M|^^||"
    "ADDRESS1^ADDRESS2^ADDRESS3^ADDRESS4^XX99 9XX^^H~^^^^^^||^^^~|||||||||||||||||||01\r"
    "PD1|||^^W99999^|G7777777\r"
    "PV1||\r"
)


class TestPhwHL7Validator(unittest.TestCase):
    def test_phw_pid7_missing_or_empty_raises_exception(self) -> None:
        phw_msh_segment = (
            "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|"
            "202505052323326666666666|P|2.5|||||GBR||EN\r"
        )
        invalid_pid_segments = [
            ("", "missing pid"),
            ("PID|1||123456^^^Hospital^MR||Doe^John\r", "no pid 7"),
            ("PID|||8888888^^^252^PI~6666666666^^^NHS^NH||A^B^C^^MR|||M|^^|", "empty pid 7"),
        ]

        for invalid_pid, description in invalid_pid_segments:
            with self.subTest(desc=description):
                phw_message = phw_msh_segment + invalid_pid
                print(phw_message)
                msg = parse_message(phw_message)
                validator = HL7Validator(hl7_version="2.5", sending_app="252", flow_name="phw")

                with self.assertRaises(ValidationException) as context:
                    validator.validate(msg)

                self.assertIn("PID.7 (Date of birth) is required for PHW.", str(context.exception))

    def test_phw_valid_birthdate(self) -> None:
        valid_birthdates = ["18000101", "19000202", "20000303", "20240404", "20010228"]
        for valid_birthdate in valid_birthdates:
            with self.subTest(birthdate=valid_birthdate):
                phw_message = VALID_PHW_A28_MESSAGE.format(birthdate=valid_birthdate)
                msg = parse_message(phw_message)
                validator = HL7Validator(hl7_version="2.5", sending_app="252", flow_name="phw")

                validator.validate(msg)

    def test_phw_invalid_birthdate_format_non_digits_length_raises_exception(self) -> None:
        invalid_birthdates = [
            "1987-01-01",
            "19870A01",
            "1987/01/01",
            "19870101.",
            "00000000",
            "199701",
            "199701011",
            "19970101123456",
            "1997",
            '""',
        ]

        for invalid_birthdate in invalid_birthdates:
            with self.subTest(birthdate=invalid_birthdate):
                phw_message = VALID_PHW_A28_MESSAGE.format(birthdate=invalid_birthdate)
                msg = parse_message(phw_message)
                validator = HL7Validator(hl7_version="2.5", sending_app="252", flow_name="phw")

                with self.assertRaises(ValidationException) as context:
                    validator.validate(msg)

                self.assertIn(
                    "PID.7 (Date of birth) must be a valid date in YYYYMMDD format for PHW", str(context.exception)
                )

    def test_phw_invalid_birthdate_year_before_1800_raises_exception(self) -> None:
        invalid_year_birthdates = ["17990101", "14530123"]

        for invalid_birthdate in invalid_year_birthdates:
            with self.subTest(birthdate=invalid_birthdate):
                phw_message = VALID_PHW_A28_MESSAGE.format(birthdate=invalid_birthdate)
                msg = parse_message(phw_message)
                validator = HL7Validator(hl7_version="2.5", sending_app="252", flow_name="phw")

                with self.assertRaises(ValidationException) as context:
                    validator.validate(msg)

                self.assertIn(
                    "PID.7 (Date of birth) - year of birth must be 1800 or later for PHW", str(context.exception)
                )

    def test_phw_validation_with_standard_validation_failure_invalid_sending_app(self) -> None:
        phw_message = VALID_PHW_A28_MESSAGE.format(birthdate="19870405")
        msg = parse_message(phw_message)

        # wrong sending app
        validator = HL7Validator(hl7_version="2.5", sending_app="999", flow_name="phw")

        with self.assertRaises(ValidationException) as context:
            validator.validate(msg)

        self.assertIn("not in allowed authority codes", str(context.exception))

    def test_phw_standard_validation_failure_wrong_message_version(self) -> None:
        phw_message = VALID_PHW_A28_MESSAGE.format(birthdate="19870405")
        msg = parse_message(phw_message)

        # wrong message version
        validator = HL7Validator(hl7_version="2.3", sending_app="252", flow_name="phw")

        with self.assertRaises(ValidationException) as context:
            validator.validate(msg)

        self.assertIn("Message has wrong version", str(context.exception))
