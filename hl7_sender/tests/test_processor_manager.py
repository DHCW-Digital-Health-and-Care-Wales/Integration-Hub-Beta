import signal
import unittest
from types import FrameType
from typing import Optional
from unittest.mock import MagicMock, patch

from hl7_sender.processor_manager import ProcessorManager


class TestProcessorManager(unittest.TestCase):

    def setUp(self) -> None:
        self.processor_manager = ProcessorManager()

    def test_initialization_sets_running_to_true(self) -> None:
        # Assert
        self.assertTrue(self.processor_manager.is_running)

    @patch('hl7_sender.processor_manager.signal.signal')
    def test_setup_signal_handlers_registers_signals(self, mock_signal: MagicMock) -> None:
        # Arrange & Act
        processor_manager = ProcessorManager()

        # Assert
        mock_signal.assert_any_call(signal.SIGINT, processor_manager._shutdown_handler)
        mock_signal.assert_any_call(signal.SIGTERM, processor_manager._shutdown_handler)
        self.assertEqual(mock_signal.call_count, 2)

    @patch('hl7_sender.processor_manager.logger')
    def test_shutdown_handler_stops_processor_and_logs(self, mock_logger: MagicMock) -> None:
        # Arrange
        signum = signal.SIGINT
        frame: Optional[FrameType] = None

        # Act
        self.processor_manager._shutdown_handler(signum, frame)

        # Assert
        self.assertFalse(self.processor_manager.is_running)
        mock_logger.info.assert_called_once_with("Shutting down the processor")

    @patch('hl7_sender.processor_manager.logger')
    def test_shutdown_handler_with_sigterm(self, mock_logger: MagicMock) -> None:
        # Arrange
        signum = signal.SIGTERM
        frame: Optional[FrameType] = None

        # Act
        self.processor_manager._shutdown_handler(signum, frame)

        # Assert
        self.assertFalse(self.processor_manager.is_running)
        mock_logger.info.assert_called_once_with("Shutting down the processor")

    @patch('hl7_sender.processor_manager.logger')
    def test_stop_method_sets_running_false_and_logs(self, mock_logger: MagicMock) -> None:
        # Arrange
        self.assertTrue(self.processor_manager.is_running)

        # Act
        self.processor_manager.stop()

        # Assert
        self.assertFalse(self.processor_manager.is_running)
        mock_logger.info.assert_called_once_with("Manual processor stop requested")

if __name__ == '__main__':
    unittest.main()
