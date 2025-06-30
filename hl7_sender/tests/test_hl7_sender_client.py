import unittest
from unittest.mock import Mock, patch
import socket

from hl7_sender.hl7_sender_client import is_socket_closed, HL7SenderClient


class TestIsSocketClosed(unittest.TestCase):

    def test_socket_open_blocking_io_error(self):
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.side_effect = BlockingIOError
        self.assertFalse(is_socket_closed(mock_socket))

    def test_socket_closed_empty_data(self):
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.return_value = b''
        self.assertTrue(is_socket_closed(mock_socket))

    def test_socket_closed_connection_reset(self):
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.side_effect = ConnectionResetError
        self.assertTrue(is_socket_closed(mock_socket))

    def test_socket_closed_unexpected_exception(self):
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.side_effect = RuntimeError("Some unexpected error")
        with self.assertLogs('hl7_sender.hl7_sender_client', level='ERROR') as cm:
            self.assertFalse(is_socket_closed(mock_socket))
            self.assertIn("unexpected exception", cm.output[0])


class TestHL7SenderClient(unittest.TestCase):

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_socket_open(self, mock_mllp_cls):
        mock_mllp = Mock()
        mock_mllp.socket = Mock()
        mock_mllp.send_message.return_value = b'ACK'
        mock_mllp_cls.return_value = mock_mllp

        # simulate open socket by mocking is_socket_closed
        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=False):
            client = HL7SenderClient('localhost', 1234)
            response = client.send_message('MSH|...')
            self.assertEqual(response, 'ACK')
            mock_mllp.send_message.assert_called_once_with('MSH|...')

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_send_message_socket_closed_triggers_reconnect(self, mock_mllp_cls):
        mock_mllp1 = Mock()
        mock_mllp1.socket = Mock()
        mock_mllp2 = Mock()
        mock_mllp2.send_message.return_value = b'ACK'

        # Simulate the first call creates mock_mllp1, second creates mock_mllp2
        mock_mllp_cls.side_effect = [mock_mllp1, mock_mllp2]

        with patch('hl7_sender.hl7_sender_client.is_socket_closed', return_value=True):
            client = HL7SenderClient('localhost', 1234)
            response = client.send_message('MSH|...')
            self.assertEqual(response, 'ACK')
            mock_mllp1.close.assert_called_once()
            mock_mllp2.send_message.assert_called_once_with('MSH|...')

    @patch('hl7_sender.hl7_sender_client.MLLPClient')
    def test_context_manager_closes_connection(self, mock_mllp_cls):
        mock_mllp = Mock()
        mock_mllp.socket = Mock()
        mock_mllp_cls.return_value = mock_mllp

        with HL7SenderClient('localhost', 1234):
            pass
        mock_mllp.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
