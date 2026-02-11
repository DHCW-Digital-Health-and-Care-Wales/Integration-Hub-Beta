import threading
import time
import unittest
from typing import List
from unittest.mock import MagicMock

from azure.servicebus.exceptions import (
    MessageSizeExceededError,
    OperationTimeoutError,
    ServiceBusError,
)

from message_bus_lib.message_sender_client import MessageSenderClient


class TestMessageSenderClient(unittest.TestCase):

    def setUp(self) -> None:
        self.TOPIC_NAME = "test-topic"
        self.service_bus_sender_client = MagicMock()
        self.message_sender_client = MessageSenderClient(self.service_bus_sender_client, self.TOPIC_NAME)

    def test_send_message_sends_message_to_service_bus_without_session(self) -> None:
        # Arrange
        message = b"Test Message"

        # Act
        self.message_sender_client.send_message(message)

        # Assert
        self.service_bus_sender_client.send_messages.assert_called_once()
        messge_sent = self.service_bus_sender_client.send_messages.call_args[0][0]
        self.assertIsNone(messge_sent.session_id)

    def test_send_message_with_session(self) -> None:
        # Arrange
        message = b"Test Message"
        session_id = "test-session-id"
        message_sender_client = MessageSenderClient(
            self.service_bus_sender_client, self.TOPIC_NAME, session_id=session_id
        )

        # Act
        message_sender_client.send_message(message)

        # Assert
        self.service_bus_sender_client.send_messages.assert_called_once()
        messge_sent = self.service_bus_sender_client.send_messages.call_args[0][0]
        self.assertEqual(messge_sent.session_id, session_id)

    def test_send_message_retries_on_failure(self) -> None:
        # Arrange
        message = b"Test Message"
        self.service_bus_sender_client.send_messages = MagicMock(side_effect=OperationTimeoutError())

        # Act
        self.message_sender_client.send_message(message)

        # Assert
        self.assertEqual(len(self.service_bus_sender_client.send_messages.mock_calls), 3)

    def test_exit_service_bus_sender_client_closed(self) -> None:
        # Arrange
        exc_type = ValueError
        exc_value = ValueError("test error")
        exc_traceback = None

        # Act
        self.message_sender_client.__exit__(exc_type, exc_value, exc_traceback)

        # Assert
        self.service_bus_sender_client.close.assert_called_once()

    def test_send_message_thread_safety(self) -> None:
        # Arrange
        running = False
        monitor_lock = threading.Lock()
        errors: List[Exception] = []

        def slow_send_messages(message: MagicMock) -> None:
            """Simulates a slow send operation that fails if accessed concurrently."""
            nonlocal running
            with monitor_lock:
                if running:
                    # Simulate the behavior of the underlying SDK when accessed concurrently
                    # The Azure SDK is not thread-safe for a single sender and may raise AttributeError or similar
                    raise AttributeError("'NoneType' object has no attribute 'client_ready'")
                running = True

            try:
                time.sleep(0.05)  # 50ms delay to ensure overlap would occur without lock
            finally:
                with monitor_lock:
                    running = False

        self.service_bus_sender_client.send_messages = MagicMock(side_effect=slow_send_messages)

        threads: List[threading.Thread] = []
        num_threads = 5

        def target() -> None:
            try:
                # We simply send a message. If the lock is missing, multiple threads will enter
                # slow_send_messages at the same time, triggering the AttributeError.
                self.message_sender_client.send_message(b"Thread Safe Test")
            except Exception as e:
                with monitor_lock:
                    errors.append(e)

        # Act - Start multiple threads simultaneously
        for _ in range(num_threads):
            thread = threading.Thread(target=target)
            threads.append(thread)

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Assert - No errors should have occurred
        if errors:
            self.fail(f"Thread safety test failed. Concurrent access exceptions occurred: {errors[0]}")

        self.assertEqual(self.service_bus_sender_client.send_messages.call_count, num_threads)

    def test_send_text_message_sends_encoded_message(self) -> None:
        # Arrange
        message_text = "Hello World"

        # Act
        self.message_sender_client.send_text_message(message_text)

        # Assert
        self.service_bus_sender_client.send_messages.assert_called_once()

    def test_send_message_with_custom_properties(self) -> None:
        # Arrange
        message = b"Test Message"
        custom_properties = {"key": "value"}

        # Act
        self.message_sender_client.send_message(message, custom_properties)

        # Assert
        self.service_bus_sender_client.send_messages.assert_called_once()
        message_sent = self.service_bus_sender_client.send_messages.call_args[0][0]
        self.assertEqual(message_sent.application_properties, {"key": "value"})

    def test_send_message_raises_message_size_exceeded_error(self) -> None:
        # Arrange
        message = b"Test Message"
        self.service_bus_sender_client.send_messages = MagicMock(
            side_effect=MessageSizeExceededError()
        )

        # Act & Assert
        with self.assertRaises(MessageSizeExceededError):
            self.message_sender_client.send_message(message)

        # Verify it does not retry for MessageSizeExceededError
        self.assertEqual(self.service_bus_sender_client.send_messages.call_count, 1)

    def test_send_message_raises_service_bus_error_after_retries(self) -> None:
        # Arrange
        message = b"Test Message"
        self.service_bus_sender_client.send_messages = MagicMock(
            side_effect=ServiceBusError("Connection failed")
        )

        # Act & Assert
        with self.assertRaises(ServiceBusError):
            self.message_sender_client.send_message(message)

        # Verify it retried 3 times (MAX_SERVICE_BUS_RETRIES)
        self.assertEqual(self.service_bus_sender_client.send_messages.call_count, 3)

    def test_context_manager_enter(self) -> None:
        # Act
        result = self.message_sender_client.__enter__()

        # Assert
        self.assertEqual(result, self.message_sender_client)

    def test_close_method(self) -> None:
        # Act
        self.message_sender_client.close()

        # Assert
        self.service_bus_sender_client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
