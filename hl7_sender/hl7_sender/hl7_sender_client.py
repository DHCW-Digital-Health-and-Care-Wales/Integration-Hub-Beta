import logging
import socket

from hl7.client import MLLPClient

logger = logging.getLogger(__name__)

def is_socket_closed(sock: socket.socket) -> bool:
    try:
        # this will try to read bytes without blocking and also without removing them from buffer (peek only)
        data = sock.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
        if len(data) == 0:
            return True
    except BlockingIOError:
        return False  # socket is open and reading from it would block
    except ConnectionResetError:
        return True  # socket was closed for some other reason
    except Exception:
        logger.exception("unexpected exception when checking if a socket is closed")
        return False
    return False


class HL7SenderClient:

    def __init__(self, receiver_mllp_hostname: str, receiver_mllp_port: int, ack_timeout_seconds: int):
        self.mllp_client = MLLPClient(receiver_mllp_hostname, receiver_mllp_port)
        self.receiver_mllp_hostname = receiver_mllp_hostname
        self.receiver_mllp_port = receiver_mllp_port
        self.ack_timeout_seconds = ack_timeout_seconds

    def send_message(self, message: str) -> str:
        if is_socket_closed(self.mllp_client.socket):
            self.mllp_client.close()
            self.mllp_client = MLLPClient(self.receiver_mllp_hostname, self.receiver_mllp_port)

        self.mllp_client.socket.settimeout(self.ack_timeout_seconds)

        try:
            ack_response = self.mllp_client.send_message(message).decode('utf-8')
            return ack_response
        except socket.timeout:
            raise TimeoutError(f"No ACK received within {self.ack_timeout_seconds} seconds")
        except Exception as e:
            raise ConnectionError(f"Connection error while sending message: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.mllp_client.close()
