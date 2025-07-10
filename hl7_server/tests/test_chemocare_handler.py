import unittest
from unittest.mock import ANY, MagicMock, patch

from hl7_server.chemocare_handler import ChemocareHandler
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

ACK_BUILDER_ATTRIBUTE = "hl7_server.chemocare_handler.HL7AckBuilder"


class TestChemocareHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_audit_client = MagicMock()
        self.mock_validator = MagicMock()

    def test_valid_a31_message_south_east_wales_returns_success_ack(self) -> None:
        """Test valid A31 message from South East Wales returns successful ACK"""
        handler = ChemocareHandler(VALID_CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_SUCCESS_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            
            result = handler.reply()

            # Verify successful ACK was created
            mock_instance.build_ack.assert_called_once_with("202505052323364444", ANY, "AA")
            self.assertIn("ACK_SUCCESS_CONTENT", result)
            
            # Verify message was sent to service bus
            self.mock_sender.send_text_message.assert_called_once_with(VALID_CHEMOCARE_A31_MESSAGE)
            
            # Verify audit logs
            self.mock_audit_client.log_message_received.assert_called_once()
            self.mock_audit_client.log_validation_result.assert_called_once()
            self.mock_audit_client.log_message_processed.assert_called_once()

    def test_valid_a28_message_bu_chemocare_returns_success_ack(self) -> None:
        """Test valid A28 message from BU Chemocare returns successful ACK"""
        handler = ChemocareHandler(VALID_CHEMOCARE_A28_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_SUCCESS_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            
            result = handler.reply()

            # Verify successful ACK was created with correct parameters
            mock_instance.build_ack.assert_called_once_with("202505052323364445", ANY, "AA")
            self.assertIn("ACK_SUCCESS_CONTENT", result)

    @patch("hl7_server.chemocare_handler.logger")
    def test_invalid_hl7_version_returns_failure_ack(self, mock_logger: MagicMock) -> None:
        """Test message with invalid HL7 version returns failure ACK"""
        handler = ChemocareHandler(INVALID_VERSION_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_FAILURE_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            
            result = handler.reply()

            # Verify failure ACK was created
            mock_instance.build_ack.assert_called_once_with("202505052323364448", ANY, "AR", ANY)
            self.assertIn("ACK_FAILURE_CONTENT", result)
            
            # Verify message was NOT sent to service bus
            self.mock_sender.send_text_message.assert_not_called()
            
            # Verify error was logged
            mock_logger.error.assert_called_once()
            self.mock_audit_client.log_validation_result.assert_called_once()
            self.mock_audit_client.log_message_failed.assert_called_once()

    @patch("hl7_server.chemocare_handler.logger")
    def test_invalid_authority_code_returns_failure_ack(self, mock_logger: MagicMock) -> None:
        """Test message with invalid authority code returns failure ACK"""
        handler = ChemocareHandler(INVALID_AUTHORITY_CODE_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_FAILURE_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            
            result = handler.reply()

            # Verify failure ACK was created
            mock_instance.build_ack.assert_called_once_with("202505052323364449", ANY, "AR", ANY)
            self.assertIn("ACK_FAILURE_CONTENT", result)
            
            # Verify message was NOT sent to service bus
            self.mock_sender.send_text_message.assert_not_called()

    @patch("hl7_server.chemocare_handler.logger")
    def test_invalid_message_type_returns_failure_ack(self, mock_logger: MagicMock) -> None:
        """Test message with unsupported message type returns failure ACK"""
        handler = ChemocareHandler(INVALID_MESSAGE_TYPE_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_FAILURE_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            
            result = handler.reply()

            # Verify failure ACK was created
            mock_instance.build_ack.assert_called_once_with("202505052323364450", ANY, "AR", ANY)
            self.assertIn("ACK_FAILURE_CONTENT", result)
            
            # Verify message was NOT sent to service bus
            self.mock_sender.send_text_message.assert_not_called()

    def test_create_successful_ack(self) -> None:
        """Test creating successful ACK message"""
        handler = ChemocareHandler(VALID_CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bSUCCESS_ACK\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            
            # Mock a parsed message for testing
            mock_msg = MagicMock()
            result = handler.create_successful_ack("12345", mock_msg)
            
            mock_instance.build_ack.assert_called_once_with("12345", mock_msg, "AA")
            self.assertEqual(result, "\x0bSUCCESS_ACK\x1c\r")

    def test_create_failure_ack(self) -> None:
        """Test creating failure ACK message"""
        handler = ChemocareHandler(VALID_CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bFAILURE_ACK\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            
            # Mock a parsed message for testing
            mock_msg = MagicMock()
            error_msg = "Test error message"
            result = handler.create_failure_ack("12345", mock_msg, error_msg)
            
            mock_instance.build_ack.assert_called_once_with("12345", mock_msg, "AR", error_msg)
            self.assertEqual(result, "\x0bFAILURE_ACK\x1c\r")

    @patch("hl7_server.chemocare_handler.logger")
    def test_successful_message_processing_audit_trail(self, mock_logger: MagicMock) -> None:
        """Test that successful message processing creates proper audit trail"""
        handler = ChemocareHandler(VALID_CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            
            handler.reply()

            # Verify correct audit calls were made
            self.mock_audit_client.log_message_received.assert_called_once_with(
                VALID_CHEMOCARE_A31_MESSAGE, "Chemocare message received"
            )
            
            # Verify validation result includes health board name
            validation_call = self.mock_audit_client.log_validation_result.call_args
            self.assertIn("South_East_Wales_Chemocare", validation_call[0][1])
            
            # Verify processing success includes health board name
            processing_call = self.mock_audit_client.log_message_processed.call_args
            self.assertIn("South_East_Wales_Chemocare", processing_call[0][1])

    @patch("hl7_server.chemocare_handler.logger") 
    def test_service_bus_failure_handling(self, mock_logger: MagicMock) -> None:
        """Test handling of service bus failures"""
        handler = ChemocareHandler(VALID_CHEMOCARE_A31_MESSAGE, self.mock_sender, self.mock_audit_client, self.mock_validator)
        
        # Mock service bus failure
        self.mock_sender.send_text_message.side_effect = Exception("Service Bus connection failed")
        
        with self.assertRaises(Exception):
            handler.reply()
            
        # Verify the message sending was attempted
        self.mock_sender.send_text_message.assert_called_once_with(VALID_CHEMOCARE_A31_MESSAGE)


if __name__ == "__main__":
    unittest.main() 