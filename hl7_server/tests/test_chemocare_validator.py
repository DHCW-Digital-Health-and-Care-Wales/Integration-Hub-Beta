import unittest

from hl7apy.parser import parse_message

from hl7_server.chemocare_validator import ChemocareValidator
from hl7_server.hl7_validator import ValidationException

# Sample valid Chemocare HL7 v2.4 A31 message from South_East_Wales_Chemocare
VALID_CHEMOCARE_A31_MESSAGE = (
    "MSH|^~\\&|245|245|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Sample valid Chemocare HL7 v2.4 A28 message from BU_CHEMOCARE_TO_MPI
VALID_CHEMOCARE_A28_MESSAGE = (
    "MSH|^~\\&|212|212|100|100|2025-05-05 23:23:32||ADT^A28^ADT_A05|202505052323364445|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Sample valid Chemocare HL7 v2.4 A40 message from South_West_Wales_Chemocare
VALID_CHEMOCARE_A40_MESSAGE = (
    "MSH|^~\\&|192|192|100|100|2025-05-05 23:23:32||ADT^A40^ADT_A39|202505052323364446|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Sample valid Chemocare HL7 v2.4 message from VEL_Chemocare_Demographics_To_MPI
VALID_CHEMOCARE_VEL_MESSAGE = (
    "MSH|^~\\&|224|224|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364447|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Invalid messages for testing
INVALID_VERSION_MESSAGE = (
    "MSH|^~\\&|245|245|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364448|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

INVALID_AUTHORITY_CODE_MESSAGE = (
    "MSH|^~\\&|999|999|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364449|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

INVALID_MESSAGE_TYPE_MESSAGE = (
    "MSH|^~\\&|245|245|100|100|2025-05-05 23:23:32||ADT^A01^ADT_A01|202505052323364450|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)


class TestChemocareValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ChemocareValidator()

    def test_valid_a31_message_south_east_wales(self) -> None:
        """Test valid A31 message from South East Wales Chemocare"""
        msg = parse_message(VALID_CHEMOCARE_A31_MESSAGE)
        authority_code = self.validator.validate(msg)
        
        self.assertEqual(authority_code, "245")
        self.assertEqual(self.validator.get_health_board_name(authority_code), "South_East_Wales_Chemocare")

    def test_valid_a28_message_bu_chemocare(self) -> None:
        """Test valid A28 message from BU Chemocare"""
        msg = parse_message(VALID_CHEMOCARE_A28_MESSAGE)
        authority_code = self.validator.validate(msg)
        
        self.assertEqual(authority_code, "212")
        self.assertEqual(self.validator.get_health_board_name(authority_code), "BU_CHEMOCARE_TO_MPI")

    def test_valid_a40_message_south_west_wales(self) -> None:
        """Test valid A40 message from South West Wales Chemocare"""
        msg = parse_message(VALID_CHEMOCARE_A40_MESSAGE)
        authority_code = self.validator.validate(msg)
        
        self.assertEqual(authority_code, "192")
        self.assertEqual(self.validator.get_health_board_name(authority_code), "South_West_Wales_Chemocare")

    def test_valid_message_vel_chemocare(self) -> None:
        """Test valid message from VEL Chemocare Demographics"""
        msg = parse_message(VALID_CHEMOCARE_VEL_MESSAGE)
        authority_code = self.validator.validate(msg)
        
        self.assertEqual(authority_code, "224")
        self.assertEqual(self.validator.get_health_board_name(authority_code), "VEL_Chemocare_Demographics_To_MPI")

    def test_invalid_hl7_version(self) -> None:
        """Test message with invalid HL7 version (2.5 instead of 2.4)"""
        msg = parse_message(INVALID_VERSION_MESSAGE)
        
        with self.assertRaises(ValidationException) as context:
            self.validator.validate(msg)
        
        self.assertIn("Invalid HL7 version", str(context.exception))
        self.assertIn("Expected 2.4, got 2.5", str(context.exception))

    def test_invalid_authority_code(self) -> None:
        """Test message with invalid authority code"""
        msg = parse_message(INVALID_AUTHORITY_CODE_MESSAGE)
        
        with self.assertRaises(ValidationException) as context:
            self.validator.validate(msg)
        
        self.assertIn("Invalid authority code", str(context.exception))
        self.assertIn("Expected one of ['245', '212', '192', '224']", str(context.exception))

    def test_invalid_message_type(self) -> None:
        """Test message with unsupported message type (A01 instead of A31/A28/A40)"""
        msg = parse_message(INVALID_MESSAGE_TYPE_MESSAGE)
        
        with self.assertRaises(ValidationException) as context:
            self.validator.validate(msg)
        
        self.assertIn("Unsupported message type", str(context.exception))
        self.assertIn("Expected one of ['A31', 'A28', 'A40']", str(context.exception))

    def test_get_health_board_name_unknown_code(self) -> None:
        """Test get_health_board_name with unknown authority code"""
        result = self.validator.get_health_board_name("999")
        self.assertEqual(result, "Unknown")

    def test_supported_message_types(self) -> None:
        """Test that all required message types are supported"""
        expected_types = ["A31", "A28", "A40"]
        self.assertEqual(self.validator.supported_message_types, expected_types)

    def test_required_hl7_version(self) -> None:
        """Test that the required HL7 version is 2.4"""
        self.assertEqual(self.validator.required_hl7_version, "2.4")

    def test_valid_authority_codes(self) -> None:
        """Test that all required authority codes are configured"""
        expected_codes = {
            "245": "South_East_Wales_Chemocare",
            "212": "BU_CHEMOCARE_TO_MPI",
            "192": "South_West_Wales_Chemocare",
            "224": "VEL_Chemocare_Demographics_To_MPI"
        }
        self.assertEqual(self.validator.valid_authority_codes, expected_codes)


if __name__ == "__main__":
    unittest.main() 