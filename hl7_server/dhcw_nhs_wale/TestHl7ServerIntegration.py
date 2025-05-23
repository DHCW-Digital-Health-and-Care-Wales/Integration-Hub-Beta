import threading
import socket
import time
import unittest

# Constants for framing HL7 with MLLP
MLLP_START = b'\x0b'
MLLP_END = b'\x1c'
CARRIAGE_RETURN = b'\x0d'

# Host/port
HOST = '127.0.0.1'
PORT = 2576  # Use a test-safe port

# Your server
from hl7_server_application import Hl7ServerApplication  # Replace with actual import

class TestHl7ServerIntegration(unittest.TestCase):
    def setUp(self):
        self.server = Hl7ServerApplication()
        self.server_thread = threading.Thread(target=self.server.start_server, kwargs={'host': HOST, 'port': PORT})
        self.server_thread.daemon = True
        self.server_thread.start()
        time.sleep(0.5)  # Give the server time to start

    def tearDown(self):
        self.server.terminated = True
        self.server_thread.join(timeout=2)

    def test_send_mllp_hl7_message_and_receive_ack(self):
        # Prepare HL7 message
        hl7_msg = b'MSH|^~\\&|App|Fac|App|Fac|202005011230||ADT^A01|123456|P|2.3\r'
        wrapped_msg = MLLP_START + hl7_msg + MLLP_END + CARRIAGE_RETURN

        with socket.create_connection((HOST, PORT), timeout=2) as sock:
            sock.sendall(wrapped_msg)

            # Receive ACK
            ack = sock.recv(1024)
            self.assertTrue(ack.startswith(MLLP_START))
            self.assertIn(b'ACK', ack)
            self.assertTrue(ack.endswith(MLLP_END + CARRIAGE_RETURN))

