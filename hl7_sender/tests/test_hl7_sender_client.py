import socket
import unittest
from unittest.mock import Mock, patch

from hl7_sender.hl7_sender_client import HL7SenderClient, is_socket_closed


class TestIsSocketClosed(unittest.TestCase):

    def test_socket_open_blocking_io_error(self) -> None:
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.side_effect = BlockingIOError
        self.assertFalse(is_socket_closed(mock_socket))

    def test_socket_closed_empty_data(self) -> None:
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.return_value = b''
        self.assertTrue(is_socket_closed(mock_socket))

    def test_socket_closed_connection_reset(self) -> None:
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.side_effect = ConnectionResetError
        self.assertTrue(is_socket_closed(mock_socket))

    def test_socket_closed_unexpected_exception(self) -> None:
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.side_effect = RuntimeError("Some unexpected error")
        with self.assertLogs('hl7_sender.hl7_sender_client', level='ERROR') as cm:
            self.assertFalse(is_socket_closed(mock_socket))
            self.assertIn("unexpected exception", cm.output[0])


class TestHL7SenderClient(unittest.TestCase):

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_socket_open(self, mock_mllp_cls: Mock) -> None:
        mock_mllp = Mock()
        mock_mllp.socket = Mock()
        mock_mllp.send_message.return_value = b'ACK'
        mock_mllp_cls.return_value = mock_mllp

        # simulate open socket by mocking is_socket_closed
        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=False):
            client = HL7SenderClient('localhost', 1234, 30)
            response = client.send_message('MSH|...')
            self.assertEqual(response, 'ACK')
            mock_mllp.send_message.assert_called_once_with('MSH|...')
            mock_mllp.socket.settimeout.assert_called_once_with(30)

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_socket_closed_triggers_reconnect(self, mock_mllp_cls: Mock) -> None:
        mock_mllp1 = Mock()
        mock_mllp1.socket = Mock()
        mock_mllp2 = Mock()
        mock_mllp2.send_message.return_value = b'ACK'

        # Simulate the first call creates mock_mllp1, second creates mock_mllp2
        mock_mllp_cls.side_effect = [mock_mllp1, mock_mllp2]

        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=True):
            client = HL7SenderClient('localhost', 1234, 40)
            response = client.send_message('MSH|...')
            self.assertEqual(response, 'ACK')
            mock_mllp1.close.assert_called_once()
            mock_mllp2.send_message.assert_called_once_with('MSH|...')
            mock_mllp2.socket.settimeout.assert_called_once_with(40)

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_timeout_error(self, mock_mllp_cls: Mock) -> None:
        mock_mllp = Mock()
        mock_mllp.socket = Mock()
        mock_mllp.send_message.side_effect = socket.timeout
        mock_mllp_cls.return_value = mock_mllp

        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=False):
            client = HL7SenderClient('localhost', 1234, 30)
            with self.assertRaises(TimeoutError) as context:
                client.send_message('MSH|...')
            self.assertIn("No ACK received within 30 seconds", str(context.exception))

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_context_manager_closes_connection(self, mock_mllp_cls: Mock) -> None:
        mock_mllp = Mock()
        mock_mllp.socket = Mock()
        mock_mllp_cls.return_value = mock_mllp

        with HL7SenderClient('localhost', 1234, 30):
            pass
        mock_mllp.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
