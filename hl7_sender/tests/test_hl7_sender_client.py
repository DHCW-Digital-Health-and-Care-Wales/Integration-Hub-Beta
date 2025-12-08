import socket
import unittest
from typing import Any, Callable, Dict
from unittest.mock import Mock, patch

from hl7_sender.hl7_sender_client import HL7SenderClient, is_socket_closed


class TestIsSocketClosed(unittest.TestCase):

    @patch('hl7_sender.hl7_sender_client.select.select')
    def test_socket_not_readable_no_data_available(self, mock_select: Mock) -> None:
        # Arrange
        mock_socket = Mock(spec=socket.socket)
        # Simulate select.select returning empty readable list (no data available)
        mock_select.return_value = ([], [], [])

        # Act
        result = is_socket_closed(mock_socket)

        # Assert
        self.assertFalse(result)
        mock_select.assert_called_once_with([mock_socket], [], [], 0)
        # recv should not be called when socket is not readable
        mock_socket.recv.assert_not_called()

    @patch('hl7_sender.hl7_sender_client.select.select')
    def test_socket_readable_with_data_socket_open(self, mock_select: Mock) -> None:
        # Arrange
        mock_socket = Mock(spec=socket.socket)
        # Simulate select.select returning the socket in readable list
        mock_select.return_value = ([mock_socket], [], [])
        mock_socket.recv.return_value = b'some data here'

        # Act
        result = is_socket_closed(mock_socket)

        # Assert
        self.assertFalse(result)
        mock_select.assert_called_once_with([mock_socket], [], [], 0)
        mock_socket.recv.assert_called_once_with(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)

    @patch('hl7_sender.hl7_sender_client.select.select')
    def test_socket_readable_with_empty_data_socket_closed(self, mock_select: Mock) -> None:
        # Arrange
        mock_socket = Mock(spec=socket.socket)
        # Simulate select.select returning the socket in readable list
        mock_select.return_value = ([mock_socket], [], [])
        # Simulate recv returning empty data (EOF - socket closed)
        mock_socket.recv.return_value = b''

        # Act
        result = is_socket_closed(mock_socket)

        # Assert
        self.assertTrue(result)
        mock_select.assert_called_once_with([mock_socket], [], [], 0)
        mock_socket.recv.assert_called_once_with(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)

    @patch('hl7_sender.hl7_sender_client.select.select')
    def test_socket_recv_raises_blocking_io_error(self, mock_select: Mock) -> None:
        # Arrange
        mock_socket = Mock(spec=socket.socket)
        mock_select.return_value = ([mock_socket], [], [])
        mock_socket.recv.side_effect = BlockingIOError

        # Act
        result = is_socket_closed(mock_socket)

        # Assert
        self.assertFalse(result)
        mock_select.assert_called_once_with([mock_socket], [], [], 0)

    @patch('hl7_sender.hl7_sender_client.select.select')
    def test_socket_recv_raises_connection_reset_error(self, mock_select: Mock) -> None:
        # Arrange
        mock_socket = Mock(spec=socket.socket)
        mock_select.return_value = ([mock_socket], [], [])
        mock_socket.recv.side_effect = ConnectionResetError

        # Act
        result = is_socket_closed(mock_socket)

        # Assert
        self.assertTrue(result)
        mock_select.assert_called_once_with([mock_socket], [], [], 0)

    @patch('hl7_sender.hl7_sender_client.select.select')
    def test_socket_unexpected_exception_during_check(self, mock_select: Mock) -> None:
        # Arrange
        mock_socket = Mock(spec=socket.socket)
        mock_select.return_value = ([mock_socket], [], [])
        mock_socket.recv.side_effect = RuntimeError("Some unexpected error")

        # Act & Assert
        with self.assertLogs('hl7_sender.hl7_sender_client', level='ERROR') as log:
            result = is_socket_closed(mock_socket)

            self.assertFalse(result)
            self.assertIn("unexpected exception", log.output[0])

        mock_select.assert_called_once_with([mock_socket], [], [], 0)

    @patch('hl7_sender.hl7_sender_client.select.select')
    def test_select_itself_raises_exception(self, mock_select: Mock) -> None:
        # Arrange
        mock_socket = Mock(spec=socket.socket)
        mock_select.side_effect = OSError("select failed")

        # Act & Assert
        with self.assertLogs('hl7_sender.hl7_sender_client', level='ERROR') as log:
            result = is_socket_closed(mock_socket)

            self.assertFalse(result)
            self.assertIn("unexpected exception", log.output[0])

        mock_select.assert_called_once_with([mock_socket], [], [], 0)

class TestHL7SenderClient(unittest.TestCase):

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_socket_open(self, mock_mllp_cls: Mock) -> None:
        # Arrange
        mock_mllp = Mock()
        mock_mllp.socket = Mock()
        mock_mllp.send_message.return_value = b'ACK'
        mock_mllp_cls.return_value = mock_mllp

        # Act
        # simulate open socket by mocking is_socket_closed
        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=False):
            client = HL7SenderClient('localhost', 1234, 30)
            response = client.send_message('MSH|...')

            # Assert
            self.assertEqual(response, 'ACK')
            mock_mllp.send_message.assert_called_once_with('MSH|...')
            mock_mllp.socket.settimeout.assert_called_once_with(30)

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_socket_closed_triggers_reconnect(self, mock_mllp_cls: Mock) -> None:
        # Arrange
        mock_mllp1 = Mock()
        mock_mllp1.socket = Mock()
        mock_mllp2 = Mock()
        mock_mllp2.send_message.return_value = b'ACK'
        # Simulate the first call creates mock_mllp1, second creates mock_mllp2
        mock_mllp_cls.side_effect = [mock_mllp1, mock_mllp2]

        # Act
        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=True):
            client = HL7SenderClient('localhost', 1234, 40)
            response = client.send_message('MSH|...')

            # Assert
            self.assertEqual(response, 'ACK')
            mock_mllp1.close.assert_called_once()
            mock_mllp2.send_message.assert_called_once_with('MSH|...')
            mock_mllp2.socket.settimeout.assert_called_once_with(40)

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_timeout_retry_succeeds(self, mock_mllp_cls: Mock) -> None:
        """Test that first timeout triggers retry and succeeds on second attempt."""
        # Arrange
        mock_mllp1 = Mock()
        mock_mllp1.socket = Mock()
        mock_mllp1.send_message.side_effect = socket.timeout

        mock_mllp2 = Mock()
        mock_mllp2.socket = Mock()
        mock_mllp2.send_message.return_value = b'ACK'

        mock_mllp_cls.side_effect = [mock_mllp1, mock_mllp2]

        # Act & Assert
        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=False):
            with self.assertLogs('hl7_sender.hl7_sender_client', level='WARNING') as log:
                client = HL7SenderClient('localhost', 1234, 30)
                response = client.send_message('MSH|...')

                self.assertEqual(response, 'ACK')
                self.assertIn("Socket timeout occurred, attempting retry", log.output[0])
                # First socket should be closed after timeout
                mock_mllp1.close.assert_called_once()
                # Second socket should NOT be closed since send succeeded
                mock_mllp2.close.assert_not_called()
                mock_mllp2.send_message.assert_called_once_with('MSH|...')
                mock_mllp2.socket.settimeout.assert_called_once_with(30)

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_timeout_retry_fails_and_raises_timeout_error(self, mock_mllp_cls: Mock) -> None:
        """Test that second timeout raises error without further retry."""
        # Arrange
        mock_mllp1 = Mock()
        mock_mllp1.socket = Mock()
        mock_mllp1.send_message.side_effect = socket.timeout

        mock_mllp2 = Mock()
        mock_mllp2.socket = Mock()
        mock_mllp2.send_message.side_effect = socket.timeout

        mock_mllp3 = Mock()  # Created after second timeout when _close_and_create_new_mllp_client is called

        mock_mllp_cls.side_effect = [mock_mllp1, mock_mllp2, mock_mllp3]

        # Act & Assert
        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=False):
            client = HL7SenderClient('localhost', 1234, 30)
            with self.assertRaises(TimeoutError) as context:
                client.send_message('MSH|...')

            self.assertIn("No ACK received within 30 seconds", str(context.exception))
            mock_mllp1.close.assert_called_once()
            mock_mllp2.close.assert_called_once()
            # Verify 2 MLLPClient instances were created (initial + retry)
            self.assertEqual(mock_mllp_cls.call_count, 2)

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_connection_error(self, mock_mllp_cls: Mock) -> None:
        # Arrange
        mock_mllp = Mock()
        mock_mllp.socket = Mock()
        mock_mllp.send_message.side_effect = ConnectionError("Network error")
        mock_mllp_cls.return_value = mock_mllp

        # Act & Assert
        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=False):
            client = HL7SenderClient('localhost', 1234, 30)
            with self.assertRaises(ConnectionError) as context:
                client.send_message('MSH|...')
            self.assertIn("Connection error while sending message", str(context.exception))
            mock_mllp.close.assert_called_once()

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test__close_and_create_new_mllp_client_closes_existing_connection(self, mock_mllp_cls: Mock) -> None:
        # Arrange
        mock_mllp1 = Mock()
        mock_mllp2 = Mock()
        mock_mllp_cls.side_effect = [mock_mllp1, mock_mllp2]

        # Act
        client = HL7SenderClient('localhost', 1234, 30)
        client.mllp_client = client._close_and_create_new_mllp_client()

        # Assert
        mock_mllp1.close.assert_called_once()
        self.assertEqual(client.mllp_client, mock_mllp2)

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test__close_and_create_new_mllp_client_handles_close_exception(self, mock_mllp_cls: Mock) -> None:
        # Arrange
        mock_mllp1 = Mock()
        mock_mllp1.close.side_effect = OSError("Failed to close socket")
        mock_mllp2 = Mock()
        mock_mllp_cls.side_effect = [mock_mllp1, mock_mllp2]

        # Act & Assert
        with self.assertLogs('hl7_sender.hl7_sender_client', level='ERROR') as log:
            client = HL7SenderClient('localhost', 1234, 30)
            client.mllp_client = client._close_and_create_new_mllp_client()

            self.assertEqual(len(log.output), 1)
            self.assertIn("Error closing socket", log.output[0])
            self.assertIn("Failed to close socket", log.output[0])

        mock_mllp1.close.assert_called_once()
        self.assertEqual(client.mllp_client, mock_mllp2)

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_context_manager_closes_connection(self, mock_mllp_cls: Mock) -> None:
        # Arrange
        mock_mllp = Mock()
        mock_mllp.socket = Mock()
        mock_mllp_cls.return_value = mock_mllp

        # Act
        with HL7SenderClient('localhost', 1234, 30):
            pass

        # Assert
        mock_mllp.close.assert_called_once()

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_ack_response_handling(self, mock_mllp_cls: Mock) -> None:
        test_cases: list[Dict[str, Any]] = [
            {
                'name': 'strips_complete_encoding_chars',
                'encoded_response': lambda content: ("\x0b" + content + "\x1c" + "\r").encode('utf-8'),
                'description': 'Complete MLLP framing with start block, end block, and CR'
            },
            {
                'name': 'strips_partial_encoding_chars',
                'encoded_response': lambda content: ("\x0b" + content + "\r").encode('utf-8'),
                'description': 'Partial MLLP framing with start block and CR (missing end block)'
            },
            {
                'name': 'handles_plain_response',
                'encoded_response': lambda content: content.encode('utf-8'),
                'description': 'Plain ACK response without any MLLP encoding characters'
            }
        ]

        for test_case in test_cases:
            with self.subTest(scenario=test_case['name']):
                # Arrange
                mock_mllp = Mock()
                mock_mllp.socket = Mock()
                mock_mllp_cls.return_value = mock_mllp

                ack_content = "MSH|^~\\&|RECEIVING_APP|RECEIVING_FACILITY|SENDING_APP|SENDING_FACILITY||ACK"
                encoded_response_func: Callable[[str], bytes] = test_case['encoded_response']
                encoded_ack = encoded_response_func(ack_content)
                mock_mllp.send_message.return_value = encoded_ack

                with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=False):
                    client = HL7SenderClient('localhost', 1234, 30)

                    # Act
                    result = client.send_message('MSH|...')

                    # Assert
                    self.assertEqual(result, ack_content,
                                     f"Failed for {test_case['description']}")


if __name__ == '__main__':
    unittest.main()
