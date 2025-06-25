import unittest
from unittest.mock import MagicMock, patch

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message

from hl7_sender.application import _process_message


def _setup():
    hl7_message = Message("ADT_A01")
    hl7_message.msh.msh_10 = 'MSGID1234'
    hl7_string = hl7_message.to_er7()
    service_bus_message = ServiceBusMessage(body=hl7_string)
    mock_mllp_client = MagicMock()

    return service_bus_message, hl7_message, hl7_string, mock_mllp_client


class TestProcessMessage(unittest.TestCase):

    @patch("hl7_sender.application.parse_message")
    @patch("hl7_sender.application.get_ack_result")
    def test_process_message_success(self, mock_ack_processor, mock_parse_message):
        # Arrange
        service_bus_message, hl7_message, hl7_string, mock_mllp_client = _setup()
        mock_parse_message.return_value = hl7_message
        hl7_ack_message = "HL7 ack message"
        mock_mllp_client.send_message.return_value = hl7_ack_message

        # Act
        _process_message(service_bus_message, mock_mllp_client)

        # Assert
        mock_parse_message.assert_called_once_with(hl7_string)
        mock_mllp_client.send_message.assert_called_once_with(hl7_message.to_er7())
        mock_ack_processor.assert_called_once_with(hl7_ack_message)

if __name__ == '__main__':
    unittest.main()
