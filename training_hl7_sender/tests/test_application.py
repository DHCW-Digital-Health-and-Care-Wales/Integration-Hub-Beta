"""
These tests verify the main application logic without actually connecting
to Service Bus or an MLLP receiver.

TESTING STRATEGY:
----------------
We mock:
- ServiceBusClientFactory: Don't connect to real Service Bus
- HL7SenderClient: Don't connect to real MLLP receiver
- ProcessorManager: Control the processing loop

This allows us to test the logic without external dependencies.

PRODUCTION REFERENCE:
--------------------
See hl7_sender/tests/test_application.py for more comprehensive tests.
"""

import unittest
from unittest.mock import MagicMock, patch

# We'll test the _process_message function directly
from training_hl7_sender.application import _process_message


class TestProcessMessage(unittest.TestCase):
    """
    Tests for the _process_message callback function.

    This function is called for each message received from the queue.
    It should:
    1. Decode the message body
    2. Send via MLLP
    3. Validate the ACK
    4. Return True for success, False for failure
    """

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Sample HL7 message that would come from the queue
        self.sample_hl7 = (
            "MSH|^~\\&|TRAINING_TRANSFORMER|FAC|RECEIVER|FAC|20260125120000||ADT^A31|12345|P|2.3.1\r"
            "EVN|A31|20260125120000\r"
            "PID|||12345^^^HOSP^MRN||SMITH^JOHN||19850101|M\r"
        )

        # Sample ACK message (success)
        self.sample_ack_success = (
            "MSH|^~\\&|RECEIVER|FAC|TRAINING_TRANSFORMER|FAC|20260125120001||ACK|12345|P|2.3.1\r"
            "MSA|AA|12345|Message accepted\r"
        )

        # Sample ACK message (failure)
        self.sample_ack_failure = (
            "MSH|^~\\&|RECEIVER|FAC|TRAINING_TRANSFORMER|FAC|20260125120001||ACK|12345|P|2.3.1\r"
            "MSA|AE|12345|Application error\r"
        )

    def test_process_message_success(self) -> None:
        """
        Test that a successful send and positive ACK returns True.
        """
        # Arrange: Create mock objects
        mock_message = MagicMock()
        mock_message.body = [self.sample_hl7.encode("utf-8")]

        mock_sender = MagicMock()
        mock_sender.send_message.return_value = self.sample_ack_success
        mock_sender.receiver_mllp_hostname = "mock-receiver"
        mock_sender.receiver_mllp_port = 2591

        # Act: Process the message
        result = _process_message(mock_message, mock_sender)

        # Assert: Should return True for success
        self.assertTrue(result)
        mock_sender.send_message.assert_called_once_with(self.sample_hl7)

    def test_process_message_negative_ack(self) -> None:
        """
        Test that a negative ACK (AE) returns False.
        """
        # Arrange
        mock_message = MagicMock()
        mock_message.body = [self.sample_hl7.encode("utf-8")]

        mock_sender = MagicMock()
        mock_sender.send_message.return_value = self.sample_ack_failure
        mock_sender.receiver_mllp_hostname = "mock-receiver"
        mock_sender.receiver_mllp_port = 2591

        # Act
        result = _process_message(mock_message, mock_sender)

        # Assert: Should return False for negative ACK
        self.assertFalse(result)

    def test_process_message_timeout(self) -> None:
        """
        Test that a timeout error returns False.
        """
        # Arrange
        mock_message = MagicMock()
        mock_message.body = [self.sample_hl7.encode("utf-8")]

        mock_sender = MagicMock()
        mock_sender.send_message.side_effect = TimeoutError("No ACK received")
        mock_sender.receiver_mllp_hostname = "mock-receiver"
        mock_sender.receiver_mllp_port = 2591

        # Act
        result = _process_message(mock_message, mock_sender)

        # Assert: Should return False for timeout
        self.assertFalse(result)

    def test_process_message_connection_error(self) -> None:
        """
        Test that a connection error returns False.
        """
        # Arrange
        mock_message = MagicMock()
        mock_message.body = [self.sample_hl7.encode("utf-8")]

        mock_sender = MagicMock()
        mock_sender.send_message.side_effect = ConnectionError("Connection refused")
        mock_sender.receiver_mllp_hostname = "mock-receiver"
        mock_sender.receiver_mllp_port = 2591

        # Act
        result = _process_message(mock_message, mock_sender)

        # Assert: Should return False for connection error
        self.assertFalse(result)


class TestApplicationMain(unittest.TestCase):
    """
    Tests for the main() function.

    These tests verify that main() correctly sets up and tears down
    resources, and handles the processing loop properly.
    """

    @patch("training_hl7_sender.application.ProcessorManager")
    @patch("training_hl7_sender.application.ServiceBusClientFactory")
    @patch("training_hl7_sender.application.HL7SenderClient")
    @patch("training_hl7_sender.application.AppConfig")
    def test_main_exits_on_signal(
        self,
        mock_app_config_class: MagicMock,
        mock_sender_class: MagicMock,
        mock_factory_class: MagicMock,
        mock_processor_class: MagicMock,
    ) -> None:
        """
        Test that main() exits cleanly when ProcessorManager.is_running becomes False.
        """
        # Arrange: Set up mocks
        mock_config = MagicMock()
        mock_config.connection_string = "test-connection"
        mock_config.service_bus_namespace = None
        mock_config.ingress_queue_name = "test-queue"
        mock_config.ingress_session_id = "test-session"
        mock_config.receiver_mllp_hostname = "localhost"
        mock_config.receiver_mllp_port = 2591
        mock_config.ack_timeout_seconds = 30
        mock_app_config_class.read_env_config.return_value = mock_config

        # Processor manager returns False on first check (simulates signal)
        mock_processor = MagicMock()
        mock_processor.is_running = False  # Exit immediately
        mock_processor_class.return_value = mock_processor

        # Mock the factory and its receiver
        mock_receiver = MagicMock()
        mock_receiver.__enter__ = MagicMock(return_value=mock_receiver)
        mock_receiver.__exit__ = MagicMock(return_value=None)
        mock_factory = MagicMock()
        mock_factory.create_message_receiver_client.return_value = mock_receiver
        mock_factory_class.return_value = mock_factory

        # Mock the sender client
        mock_sender = MagicMock()
        mock_sender.__enter__ = MagicMock(return_value=mock_sender)
        mock_sender.__exit__ = MagicMock(return_value=None)
        mock_sender_class.return_value = mock_sender

        # Act: Run main (should exit immediately due to is_running=False)
        from training_hl7_sender.application import main

        main()

        # Assert: Verify setup was called
        mock_app_config_class.read_env_config.assert_called_once()
        mock_factory.create_message_receiver_client.assert_called_once()


if __name__ == "__main__":
    unittest.main()
