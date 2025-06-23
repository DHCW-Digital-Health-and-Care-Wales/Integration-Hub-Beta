import unittest
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message

from hl7_transformer.application import _process_message


def _setup(created_datetime: str):
    hl7_message = Message("ADT_A01")
    hl7_message.msh.msh_7 = created_datetime
    hl7_message.msh.msh_10 = 'MSGID1234'
    hl7_string = hl7_message.to_er7()
    service_bus_message = ServiceBusMessage(body=hl7_string)
    mock_sender = MagicMock()

    return service_bus_message, hl7_message, hl7_string, mock_sender


class TestProcessMessage(unittest.TestCase):

    @patch("hl7_transformer.application.parse_message")
    @patch("hl7_transformer.application.transform_datetime")
    def test_process_message_success(self, mock_transform_datetime, mock_parse_message):
        # Arrange
        created_datetime = "2025-05-22_10:30:00"
        service_bus_message, hl7_message, hl7_string, mock_sender = _setup(created_datetime)
        mock_parse_message.return_value = hl7_message
        mock_transform_datetime.return_value = "20250522103000"

        # Act
        result = _process_message(service_bus_message, mock_sender)

        # Assert
        mock_parse_message.assert_called_once_with(hl7_string)
        mock_transform_datetime.assert_called_once_with(created_datetime)
        mock_sender.send_message.assert_called_once_with(hl7_message.to_er7())
        self.assertTrue(result.success)

    @patch("hl7_transformer.application.parse_message")
    @patch("hl7_transformer.application.transform_datetime")
    def test_process_message_failure_due_to_transform(self, mock_transform_datetime,
                                                      mock_parse_message):
        # Arrange
        created_datetime = "invalid_datetime"
        service_bus_message, hl7_message, hl7_string, mock_sender = _setup(created_datetime)
        mock_parse_message.return_value = hl7_message
        error_reason = "Invalid date"
        mock_transform_datetime.side_effect = ValueError(error_reason)

        # Act
        result = _process_message(service_bus_message, mock_sender)

        # Assert
        mock_parse_message.assert_called_once_with(hl7_string)
        mock_transform_datetime.assert_called_once_with(created_datetime)
        mock_sender.send_message.assert_not_called()
        self.assertFalse(result.success)
        self.assertEqual(result.error_reason, error_reason)


if __name__ == '__main__':
    unittest.main()
