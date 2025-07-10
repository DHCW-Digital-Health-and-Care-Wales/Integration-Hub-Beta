import unittest
from unittest.mock import ANY, MagicMock, patch

from hl7_server.generic_handler import GenericHandler

# Sample valid Chemocare HL7 v2.4 A31 message (should be delegated)
CHEMOCARE_A31_MESSAGE = (
    "MSH|^~\\&|245|245|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.4|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Sample valid PHW HL7 message (should be processed normally)
PHW_A28_MESSAGE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

# Sample unknown authority code message (should be processed normally)
UNKNOWN_AUTHORITY_MESSAGE = (
    "MSH|^~\\&|999|999|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

ACK_BUILDER_ATTRIBUTE = "hl7_server.generic_handler.HL7AckBuilder"
CHEMOCARE_HANDLER_ATTRIBUTE = "hl7_server.chemocare_handler.ChemocareHandler"


class TestGenericHandlerChemocareDelegation(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_audit_client = MagicMock()
        self.mock_validator = MagicMock()

    def test_delegates_chemocare_message_to_chemocare_handler(self) -> None:
        """Test that Chemocare messages (authority code 245) are delegated to ChemocareHandler"""
        handler = GenericHandler(CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
            mock_chemocare_instance = mock_chemocare_handler_class.return_value
            mock_chemocare_instance.reply.return_value = "\x0bCHEMOCARE_ACK_RESPONSE\x1c\r"
            
            result = handler.reply()
            
            # Verify ChemocareHandler was instantiated with correct parameters
            mock_chemocare_handler_class.assert_called_once_with(
                CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator
            )
            
            # Verify ChemocareHandler.reply() was called
            mock_chemocare_instance.reply.assert_called_once()
            
            # Verify the response came from ChemocareHandler
            self.assertEqual(result, "\x0bCHEMOCARE_ACK_RESPONSE\x1c\r")

    def test_processes_phw_message_normally(self) -> None:
        """Test that PHW messages (non-Chemocare authority codes) are processed normally"""
        handler = GenericHandler(PHW_A28_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_ack_builder:
            with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
                mock_instance = mock_ack_builder.return_value
                mock_ack_message = MagicMock()
                mock_ack_message.to_mllp.return_value = "\x0bPHW_ACK_RESPONSE\x1c\r"
                mock_instance.build_ack.return_value = mock_ack_message
                
                result = handler.reply()
                
                # Verify ChemocareHandler was NOT called
                mock_chemocare_handler_class.assert_not_called()
                
                # Verify normal processing occurred
                self.mock_validator.validate.assert_called_once()
                self.mock_sender.send_text_message.assert_called_once_with(PHW_A28_MESSAGE)
                mock_instance.build_ack.assert_called_once()
                
                # Verify response came from normal processing
                self.assertEqual(result, "\x0bPHW_ACK_RESPONSE\x1c\r")

    def test_processes_unknown_authority_message_normally(self) -> None:
        """Test that messages with unknown authority codes are processed normally (not delegated)"""
        handler = GenericHandler(UNKNOWN_AUTHORITY_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_ack_builder:
            with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
                mock_instance = mock_ack_builder.return_value
                mock_ack_message = MagicMock()
                mock_ack_message.to_mllp.return_value = "\x0bUNKNOWN_ACK_RESPONSE\x1c\r"
                mock_instance.build_ack.return_value = mock_ack_message
                
                result = handler.reply()
                
                # Verify ChemocareHandler was NOT called
                mock_chemocare_handler_class.assert_not_called()
                
                # Verify normal processing occurred
                self.mock_validator.validate.assert_called_once()
                self.mock_sender.send_text_message.assert_called_once_with(UNKNOWN_AUTHORITY_MESSAGE)
                mock_instance.build_ack.assert_called_once()

    def test_is_chemocare_message_detection(self) -> None:
        """Test the _is_chemocare_message helper method"""
        handler = GenericHandler(PHW_A28_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        # Test Chemocare authority codes
        self.assertTrue(handler._is_chemocare_message("245"))  # South_East_Wales_Chemocare
        self.assertTrue(handler._is_chemocare_message("212"))  # BU_CHEMOCARE_TO_MPI
        self.assertTrue(handler._is_chemocare_message("192"))  # South_West_Wales_Chemocare
        self.assertTrue(handler._is_chemocare_message("224"))  # VEL_Chemocare_Demographics_To_MPI
        
        # Test non-Chemocare authority codes
        self.assertFalse(handler._is_chemocare_message("252"))  # PHW
        self.assertFalse(handler._is_chemocare_message("999"))  # Unknown
        self.assertFalse(handler._is_chemocare_message("100"))  # Unknown

    @patch("hl7_server.generic_handler.logger")
    def test_chemocare_delegation_logging(self, mock_logger: MagicMock) -> None:
        """Test that delegation to ChemocareHandler is properly logged"""
        handler = GenericHandler(CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
            mock_chemocare_instance = mock_chemocare_handler_class.return_value
            mock_chemocare_instance.reply.return_value = "\x0bCHEMOCARE_ACK\x1c\r"
            
            handler.reply()
            
            # Verify delegation was logged
            mock_logger.info.assert_any_call(
                "Received message type: %s, Control ID: %s, Authority: %s", 
                "ADT^A31^ADT_A05", "202505052323364444", "245"
            )
            mock_logger.info.assert_any_call(
                "Delegating to ChemocareHandler for authority code: %s", "245"
            )

    def test_chemocare_authority_codes_coverage(self) -> None:
        """Test that all defined Chemocare authority codes trigger delegation"""
        from hl7_server.hl7_constant import Hl7Constants
        
        for authority_code in Hl7Constants.CHEMOCARE_AUTHORITY_CODES.keys():
            # Create a message with this authority code
            test_message = (
                f"MSH|^~\\&|{authority_code}|{authority_code}|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|12345|P|2.4|||||GBR||EN\r"
                "PID|1||123456^^^Hospital^MR||Doe^John\r"
            )
            
            handler = GenericHandler(test_message, self.mock_sender, self.mock_audit_client, self.mock_validator)
            
            with patch(CHEMOCARE_HANDLER_ATTRIBUTE) as mock_chemocare_handler_class:
                mock_chemocare_instance = mock_chemocare_handler_class.return_value
                mock_chemocare_instance.reply.return_value = "\x0bTEST_ACK\x1c\r"
                
                handler.reply()
                
                # Verify delegation occurred for this authority code
                mock_chemocare_handler_class.assert_called_once()
                mock_chemocare_instance.reply.assert_called_once()
                
                # Reset mocks for next iteration
                mock_chemocare_handler_class.reset_mock()


if __name__ == "__main__":
    unittest.main() 