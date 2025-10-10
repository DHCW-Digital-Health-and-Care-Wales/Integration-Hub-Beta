import unittest
from unittest.mock import ANY, MagicMock, patch

from hl7_server.generic_handler import GenericHandler
from hl7_server.hl7_validator import HL7Validator, ValidationException

# Sample valid HL7 message (pipe & hat, type A28)
VALID_A28_MESSAGE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)

VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A28^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1|98765^^^108^MR|1000000001^^^NHS^NH~BCUCC1000000001^^^212^PI||"
    "TEST^TEST^T^^Mrs.||20000101000000|F|||TEST,^TEST^TEST TEST^^CF11 9AD||"
    "01000 000 001|07000000001|||||||||||||||2023-01-15|||0\r"
)

INVALID_MPI_OUTBOUND_MESSAGE_TYPE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A01^ADT_A01|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1|98765^^^108^MR||Doe^John\r"
)

ACK_BUILDER_ATTRIBUTE = "hl7_server.generic_handler.HL7AckBuilder"


class TestGenericHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_sender = MagicMock()
        self.mock_event_logger = MagicMock()
        self.validator = MagicMock()
        self.handler = GenericHandler(VALID_A28_MESSAGE, self.mock_sender, self.mock_event_logger, self.validator)

    def test_valid_a28_message_returns_ack(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK_CONTENT\x1c\r"
            mock_instance.build_ack.return_value = mock_ack_message
            result = self.handler.reply()

            mock_instance.build_ack.assert_called_once()
            self.assertIn("ACK_CONTENT", result)

    def test_ack_message_created_correctly(self) -> None:
        with patch(ACK_BUILDER_ATTRIBUTE) as MockAckBuilder:
            mock_builder_instance = MockAckBuilder.return_value

            # Mock the Message-like object returned from build_ack
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = (
                "\x0bMSH|^~\\&|100|100|252|252|202405280830||ACK^A28^ACK|123456|P|2.5\rMSA|AA|123456\r\x1c\r"
            )
            mock_builder_instance.build_ack.return_value = mock_ack_message

            ack_response = self.handler.reply()

            self.assertIn("MSA|AA|123456", ack_response)
            self.assertIn("ACK^A28^ACK", ack_response)
            self.assertTrue(ack_response.startswith("\x0b"))
            self.assertTrue(ack_response.endswith("\x1c\r"))

            mock_builder_instance.build_ack.assert_called_once_with("202505052323364444", ANY)
            mock_ack_message.to_mllp.assert_called_once()

    @patch("hl7_server.generic_handler.logger")
    def test_validation_exception(self, mock_logger: MagicMock) -> None:
        exception = ValidationException("Invalid sending app id")
        message = "MSH|^~\\&|100|100|100|252|202405280830||ACK^A28^ACK|123456|P|2.5\r"

        validator = MagicMock()
        validator.validate = MagicMock(side_effect=exception)
        handler = GenericHandler(message, self.mock_sender, self.mock_event_logger, validator)

        with self.assertRaises(ValidationException):
            handler.reply()

        mock_logger.error.assert_called_once_with(f"HL7 validation error: {exception}")
        self.mock_event_logger.log_message_failed.assert_called_once_with(message, f"HL7 validation error: {exception}")

    def test_message_sent_to_service_bus(self) -> None:
        self.handler.reply()

        self.mock_sender.send_text_message.assert_called_once_with(VALID_A28_MESSAGE, None)

    @patch("hl7_server.generic_handler.validate_er7_with_flow")
    def test_mpi_outbound_flow_sets_custom_properties_with_update_source(
        self, mock_validate_flow_xml: MagicMock
    ) -> None:
        sender = MagicMock()
        event_logger = MagicMock()
        validator = HL7Validator(flow_name="mpi")
        with patch(ACK_BUILDER_ATTRIBUTE) as mock_builder:
            mock_ack_instance = mock_builder.return_value
            mock_ack_message = MagicMock()
            mock_ack_message.to_mllp.return_value = "\x0bACK\x1c\r"
            mock_ack_instance.build_ack.return_value = mock_ack_message

            handler = GenericHandler(
                VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE,
                sender,
                event_logger,
                validator,
                flow_name="mpi",
            )

            handler.reply()

        mock_validate_flow_xml.assert_called_once()
        sender.send_text_message.assert_called_once_with(
            VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE,
            {
                "MessageType": "A28",
                "UpdateSource": "108",
                "AssigningAuthority": "NHS",
                "DateDeath": "2023-01-15",
                "ReasonDeath": "",
            },
        )

    @patch("hl7_server.generic_handler.validate_er7_with_flow")
    def test_mpi_outbound_flow_rejects_invalid_messages(self, mock_validate_flow_xml: MagicMock) -> None:
        exception_scenarios = [
            ("unsupported_message_type", INVALID_MPI_OUTBOUND_MESSAGE_TYPE),
            ("missing_update_source", VALID_MPI_OUTBOUND_MESSAGE_WITH_UPDATE_SOURCE.splitlines()[0]),
        ]

        for name, message in exception_scenarios:
            with self.subTest(scenario=name):
                sender = MagicMock()
                event_logger = MagicMock()
                validator = HL7Validator(flow_name="mpi")

                handler = GenericHandler(
                    message,
                    sender,
                    event_logger,
                    validator,
                    flow_name="mpi",
                )

                with self.assertRaises(ValidationException):
                    handler.reply()

                mock_validate_flow_xml.assert_not_called()
                sender.send_text_message.assert_not_called()

                mock_validate_flow_xml.reset_mock()


if __name__ == "__main__":
    unittest.main()
