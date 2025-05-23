import unittest
import socket
from unittest.mock import MagicMock, patch, call

from hl7_server_application import Hl7ServerApplication


# MLLP framing characters
MLLP_START = b'\x0b'  # VT
MLLP_END = b'\x1c'  # FS
CARRIAGE_RETURN = b'\x0d'  # CR

class TestHl7ServerApplication(unittest.TestCase):

    def setUp(self):
        self.server = Hl7ServerApplication()
        self.server.terminated = False  # Avoid signal handling in tests

    @patch('hl7_server_application.logger')
    def test_handle_hl7_message_returns_ack(self, mock_logger):
        hl7_msg = b'MSH|^~\\&|SendingApp|SendingFac|ReceivingApp|ReceivingFac|202005011230||ADT^A01|123456|P|2.5\r'
        response = self.server.handle_hl7_message(hl7_msg)
        self.assertEqual(response, b'ACK')

    @patch('hl7_server_application.logger')
    def test_handle_client_processes_valid_hl7_message(self, mock_logger):
        fake_socket = MagicMock()
        hl7_msg = b'MSH|^~\\&|App|Fac|App|Fac|202005011230||ORM^O01|1234|P|2.3\r'
        framed_msg = MLLP_START + hl7_msg + MLLP_END + CARRIAGE_RETURN
        fake_socket.recv.side_effect = [framed_msg, b'']

        with patch.object(self.server, 'handle_hl7_message', return_value=b'ACK') as mock_handler:
            self.server.handle_client(fake_socket)

        self.assertTrue(mock_handler.called)
        sent_data = fake_socket.sendall.call_args[0][0]
        self.assertIn(b'ACK', sent_data)


    @patch('hl7_server_application.socket.socket')  # Mock the socket class
    @patch('hl7_server_application.logger')         # Optional: Mock logger to suppress output
    def test_start_server_accepts_and_handles_connection(self, mock_logger, mock_socket_class):
        # Create mock socket instance to be used with 'with' statement
        mock_server_socket = MagicMock()
        mock_conn = MagicMock()

        # Context manager return value
        mock_socket_class.return_value.__enter__.return_value = mock_server_socket

        # Simulate accept() returns a connection once, then triggers socket.timeout
        mock_server_socket.accept.side_effect = [
            (mock_conn, ('127.0.0.1', 12345)),
            socket.timeout(),  # triggers the loop to continue
        ]

        # Simulate a second loop iteration triggers termination
        app = Hl7ServerApplication()

        # We'll patch handle_client to avoid real client logic
        with patch.object(app, 'handle_client') as mock_handle_client:
            # Simulate termination after first connection
            def stop_after_call(*args, **kwargs):
                app.terminated = True
            mock_handle_client.side_effect = stop_after_call

            app.start_server(host='inseprodphwdemographics.cymru.nhs.uk', port=20001)

        # Assertions
        mock_socket_class.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_server_socket.bind.assert_called_once_with(('inseprodphwdemographics.cymru.nhs.uk', 20001))
        mock_server_socket.listen.assert_called_once()
        self.assertTrue(mock_handle_client.called)
        mock_server_socket.accept.assert_called()
        mock_conn.__enter__.assert_called()  # Confirms context manager on connection


