import logging
import select
import socket
from typing import Any, Optional, Type

from hl7.client import MLLPClient
from hl7apy.consts import MLLP_ENCODING_CHARS

logger = logging.getLogger(__name__)
ENCODING_CHARS = MLLP_ENCODING_CHARS.SB + MLLP_ENCODING_CHARS.EB + MLLP_ENCODING_CHARS.CR


def is_socket_closed(sock: socket.socket) -> bool:
    try:
        # Check if the socket is readable (may indicate data or EOF)
        readable, _, _ = select.select([sock], [], [], 0)
        if readable:
            # this will try to read bytes without blocking and also without removing them from buffer (peek only)
            data = sock.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
            return len(data) == 0
        return False  # no data, but socket is fine
    except BlockingIOError:
        return False  # socket is open and reading from it would block
    except ConnectionResetError:
        return True  # socket was closed for some other reason
    except Exception:
        logger.exception("unexpected exception when checking if a socket is closed")
        return False

class HL7SenderClient:

    def __init__(self, receiver_mllp_hostname: str, receiver_mllp_port: int, ack_timeout_seconds: int):
        self.receiver_mllp_hostname = receiver_mllp_hostname
        self.receiver_mllp_port = receiver_mllp_port
        self.ack_timeout_seconds = ack_timeout_seconds
        self.mllp_client: MLLPClient = self._create_mllp_client()

    def _close_mllp_client(self) -> None:
        try:
            self.mllp_client.close()
        except Exception as e:
            logger.error(f"Error closing socket: {e}")

    def _create_mllp_client(self) -> MLLPClient:
        mllp_client = MLLPClient(self.receiver_mllp_hostname, self.receiver_mllp_port)
        mllp_client.socket.settimeout(self.ack_timeout_seconds)
        return mllp_client

    def _close_and_create_new_mllp_client(self) -> MLLPClient:
        self._close_mllp_client()
        return self._create_mllp_client()

    def send_message(self, message: str, _retry_attempted: bool = False) -> str:
        if is_socket_closed(self.mllp_client.socket):
            logger.info("creating new MLLP client connection")
            self.mllp_client = self._close_and_create_new_mllp_client()

        try:
            ack_response = self.mllp_client.send_message(message).decode('utf-8')
            stripped_response = ack_response.strip(ENCODING_CHARS)
            return stripped_response
        except socket.timeout:
            if not _retry_attempted:
                logger.warning("Socket timeout occurred, attempting retry with new connection...")
                self.mllp_client = self._close_and_create_new_mllp_client()
                return self.send_message(message, _retry_attempted=True)
            self.mllp_client = self._close_and_create_new_mllp_client()
            raise TimeoutError(f"No ACK received within {self.ack_timeout_seconds} seconds")
        except Exception as e:
            self.mllp_client = self._close_and_create_new_mllp_client()
            raise ConnectionError(f"Connection error while sending message: {e}")

    def __enter__(self) -> "HL7SenderClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        self.mllp_client.close()
