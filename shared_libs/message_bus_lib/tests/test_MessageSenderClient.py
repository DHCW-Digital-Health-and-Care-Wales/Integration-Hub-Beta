import threading
import time
import unittest
from typing import Any, Callable, List
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

    def _create_slow_operation(self) -> Callable[..., None]:
        """Creates a slow operation that fails if accessed concurrently."""
        lock = threading.Lock()
        is_running = False

        def slow_operation(*args: Any) -> None:
            nonlocal is_running
            with lock:
                if is_running:
                    raise AttributeError("'NoneType' object has no attribute 'client_ready'")
                is_running = True
            try:
                time.sleep(0.05)  # 50ms delay to ensure overlap would occur without lock
            finally:
                with lock:
                    is_running = False
        return slow_operation

    def _run_concurrent_operations(self, operations: List[Callable[[], None]]) -> List[Exception]:
        """Helper method to run multiple operations concurrently and collect errors."""
        errors: List[Exception] = []
        errors_lock = threading.Lock()
        threads: List[threading.Thread] = []

        def run_with_error_capture(operation: Callable[[], None]) -> None:
            try:
                operation()
            except Exception as e:
                with errors_lock:
                    errors.append(e)

        for operation in operations:
            thread = threading.Thread(target=run_with_error_capture, args=(operation,))
            threads.append(thread)

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        return errors

    def test_send_message_thread_safety(self) -> None:
        """Test that concurrent send_message() calls are serialized by the lock."""
        # Arrange
        self.service_bus_sender_client.send_messages = MagicMock(
            side_effect=self._create_slow_operation()
        )

        num_threads = 5
        operations = [lambda: self.message_sender_client.send_message(b"Thread Safe Test")] * num_threads

        # Act
        errors = self._run_concurrent_operations(operations)

        # Assert
        if errors:
            self.fail(f"Thread safety test failed. Concurrent access exceptions occurred: {errors[0]}")
        self.assertEqual(self.service_bus_sender_client.send_messages.call_count, num_threads)

    def test_close_thread_safety(self) -> None:
        """Test that concurrent close() calls are serialized by the lock."""
        # Arrange
        self.service_bus_sender_client.close = MagicMock(
            side_effect=self._create_slow_operation()
        )

        num_threads = 5
        operations = [lambda: self.message_sender_client.close()] * num_threads

        # Act
        errors = self._run_concurrent_operations(operations)

        # Assert
        if errors:
            self.fail(f"Thread safety test failed. Concurrent access exceptions occurred: {errors[0]}")
        self.assertEqual(self.service_bus_sender_client.close.call_count, num_threads)

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
