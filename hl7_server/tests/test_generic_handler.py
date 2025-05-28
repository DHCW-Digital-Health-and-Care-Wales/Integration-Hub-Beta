import unittest
from unittest.mock import patch, MagicMock,ANY
from hl7_server.hl7server.generic_handler import GenericHandler, InvalidHL7FormatException

# Sample valid HL7 message (pipe & hat, type A28)
VALID_A28_MESSAGE = (
    "MSH|^~\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)



class TestGenericHandler(unittest.TestCase):


    def test_valid_a28_message_returns_ack(self):
        self.handler = GenericHandler(VALID_A28_MESSAGE)

        with patch('hl7_server.hl7server.generic_handler.HL7AckBuilder') as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            result = self.handler.reply()

            mock_instance.build_ack.assert_called_once()
            self.assertIn("ACK_CONTENT", result)


    def test_ack_message_created_correctly(self):
        handler = GenericHandler(VALID_A28_MESSAGE)

        # Mock HL7AckBuilder methods
        with patch('hl7_server.hl7server.generic_handler.HL7AckBuilder') as MockAckBuilder:
            mock_builder_instance = MockAckBuilder.return_value

            # Mock the Message-like object returned from build_ack
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = (
                "\x0bMSH|^~\\&|100|100|252|252|202405280830||ACK^A28^ACK|123456|P|2.5\r"
                "MSA|AA|123456\r\x1c\r"
            )
            mock_builder_instance.build_ack.return_value = mock_ack_message

            ack_response = handler.reply()

            self.assertIn("MSA|AA|123456", ack_response)
            self.assertIn("ACK^A28^ACK", ack_response)
            self.assertTrue(ack_response.startswith("\x0b"))
            self.assertTrue(ack_response.endswith("\x1c\r"))

            mock_builder_instance.build_ack.assert_called_once_with("202505052323364444",ANY)
            mock_ack_message.to_mllp.assert_called_once()


if __name__ == '__main__':
    unittest.main()
