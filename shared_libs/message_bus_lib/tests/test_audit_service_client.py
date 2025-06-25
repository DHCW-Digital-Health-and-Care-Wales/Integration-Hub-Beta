import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from message_bus_lib.audit_service_client import AuditServiceClient


class TestAuditServiceClient(unittest.TestCase):

    def setUp(self):
        self.sender_client = MagicMock()
        self.workflow_id = "test-workflow"
        self.microservice_id = "test-service"
        self.audit_client = AuditServiceClient(self.sender_client, self.workflow_id, self.microservice_id)

    @patch('message_bus_lib.audit_service_client.datetime')
    def test_log_message_received(self, mock_datetime):
        # Arrange
        mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message_content = "Test HL7 Message"
        validation_result = "Valid"

        # Act
        self.audit_client.log_message_received(message_content, validation_result)

        # Assert
        self.sender_client.send_text_message.assert_called_once()
        sent_data = json.loads(self.sender_client.send_text_message.call_args[0][0])
        
        self.assertEqual(sent_data["workflow_id"], self.workflow_id)
        self.assertEqual(sent_data["microservice_id"], self.microservice_id)
        self.assertEqual(sent_data["event_type"], "MESSAGE_RECEIVED")
        self.assertEqual(sent_data["message_content"], message_content)
        self.assertEqual(sent_data["validation_result"], validation_result)

    @patch('message_bus_lib.audit_service_client.datetime')
    def test_log_message_processed(self, mock_datetime):
        # Arrange
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message_content = "Test HL7 Message"
        validation_result = "Processed successfully"

        # Act
        self.audit_client.log_message_processed(message_content, validation_result)

        # Assert
        self.sender_client.send_text_message.assert_called_once()
        sent_data = json.loads(self.sender_client.send_text_message.call_args[0][0])
        
        self.assertEqual(sent_data["event_type"], "MESSAGE_PROCESSED")
        self.assertEqual(sent_data["validation_result"], validation_result)

    @patch('message_bus_lib.audit_service_client.datetime')
    def test_log_message_failed(self, mock_datetime):
        # Arrange
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message_content = "Test HL7 Message"
        error_details = "Parsing failed"

        # Act
        self.audit_client.log_message_failed(message_content, error_details)

        # Assert
        self.sender_client.send_text_message.assert_called_once()
        sent_data = json.loads(self.sender_client.send_text_message.call_args[0][0])
        
        self.assertEqual(sent_data["event_type"], "MESSAGE_FAILED")
        self.assertEqual(sent_data["error_details"], error_details)

    @patch('message_bus_lib.audit_service_client.datetime')
    def test_log_validation_result_success(self, mock_datetime):
        # Arrange
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message_content = "Test HL7 Message"
        validation_result = "Valid HL7 format"

        # Act
        self.audit_client.log_validation_result(message_content, validation_result, is_success=True)

        # Assert
        self.sender_client.send_text_message.assert_called_once()
        sent_data = json.loads(self.sender_client.send_text_message.call_args[0][0])
        
        self.assertEqual(sent_data["event_type"], "VALIDATION_SUCCESS")
        self.assertEqual(sent_data["validation_result"], validation_result)

    @patch('message_bus_lib.audit_service_client.datetime')
    def test_log_validation_result_failed(self, mock_datetime):
        # Arrange
        mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        message_content = "Test HL7 Message"
        validation_result = "Invalid HL7 format"

        # Act
        self.audit_client.log_validation_result(message_content, validation_result, is_success=False)

        # Assert
        self.sender_client.send_text_message.assert_called_once()
        sent_data = json.loads(self.sender_client.send_text_message.call_args[0][0])
        
        self.assertEqual(sent_data["event_type"], "VALIDATION_FAILED")
        self.assertEqual(sent_data["validation_result"], validation_result)

    def test_send_audit_event_handles_exception(self):
        # Arrange
        self.sender_client.send_text_message.side_effect = Exception("Network error")
        
        # Act & Assert - should not raise exception
        self.audit_client.log_message_received("test message")

    def test_close(self):
        # Act
        self.audit_client.close()
        
        # Assert
        self.sender_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()