import unittest
from unittest.mock import ANY, MagicMock, patch

from hl7_mock_receiver.generic_handler import GenericHandler

# Sample valid HL7 message (pipe & hat, type A28)
VALID_A28_MESSAGE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

class TestGenericHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.handler = GenericHandler(VALID_A28_MESSAGE, self.mock_sender)

    @patch("hl7_mock_receiver.generic_handler.build_ack")
    def test_valid_a28_message_returns_ack(self, mock_ack_builder: MagicMock) -> None:
        self.handler.reply()

        mock_ack_builder.assert_called_once()

    @patch("hl7_mock_receiver.generic_handler.build_nack")
    def test_message_with_fail_in_message_returns_nack(self, mock_nack_builder: MagicMock) -> None:
        fail_message = (
            "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
            "PID|1||123456^^^Hospital^MR||Doe^fail\r"
        )
        handler = GenericHandler(fail_message, self.mock_sender)
        handler.reply()

        mock_nack_builder.assert_called_once()

    def test_message_sent_to_service_bus(self) -> None:
        self.handler.reply()

        self.mock_sender.send_text_message.assert_called_once_with(VALID_A28_MESSAGE)


if __name__ == "__main__":
    unittest.main()
