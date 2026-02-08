import logging
import select
import socket
from typing import Any, Optional, Type

from hl7.client import MLLPClient
from hl7apy.consts import MLLP_ENCODING_CHARS

logger = logging.getLogger(__name__)

# MLLP framing characters that need to be stripped from responses
ENCODING_CHARS = MLLP_ENCODING_CHARS.SB + MLLP_ENCODING_CHARS.EB + MLLP_ENCODING_CHARS.CR



def is_socket_closed(sock: socket.socket) -> bool:
    """Check if a socket is closed."""
    try:
        # Use select to check if the socket is ready for reading
        rlist, _, _ = select.select([sock], [], [], 0)
        if rlist:
            # If the socket is ready for reading, check if it returns data
            data = sock.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
            return len(data) == 0  # If no data is returned, the socket is closed
        return False  # Socket is not ready for reading, so it's not closed
    except BlockingIOError:
        return False  # No data available to read, but the socket is still open
    except ConnectionResetError:
        return True  # Connection was reset, so the socket is closed
    except (socket.error, OSError):
        logger.exception("Socket error occurred while checking if socket is closed.")
        return False  # An error occurred, so we assume the socket is closed


class Hl7SenderClient:
    def __init__(self, receiver_mllp_hostname: str, receiver_mllp_port: int, ack_timeout_seconds: int) -> None:
        self.receiver_mllp_hostname = receiver_mllp_hostname
        self.receiver_mllp_port = receiver_mllp_port
        self.ack_timeout_seconds = ack_timeout_seconds

        self.mllp_client: MLLPClient = self._create_mllp_client()

    def _create_mllp_client(self) -> MLLPClient:
        mllp_client = MLLPClient(self.receiver_mllp_hostname, self.receiver_mllp_port)
        mllp_client.socket.settimeout(self.ack_timeout_seconds)
        return mllp_client

    def _close_mllp_client(self) -> None:
        # Close the MLLP client socket safely
        try:
            self.mllp_client.close()
        except Exception as e:
            logger.error(f"Error occurred while closing MLLP client socket: {e}")

    def _close_and_create_new_mllp_client(self) -> MLLPClient:
        self._close_mllp_client()
        return self._create_mllp_client()

    def send_message(self, hl7_message: str, _retry_attempted: bool = False) -> str:
        # Check if the socket connection is still alive before sending the message
        if is_socket_closed(self.mllp_client.socket):
            logger.warning("MLLP client socket is closed. Re-establishing connection.")
            self.mllp_client = self._close_and_create_new_mllp_client()

        try:
            ack_response = self.mllp_client.send_message(hl7_message).decode("utf-8").strip(ENCODING_CHARS)
            return ack_response
        except socket.timeout as e:
            if not _retry_attempted:
                logger.warning(f"Timeout while waiting for ACK: {e}. Retrying once...")
                self.mllp_client = self._close_and_create_new_mllp_client()
                return self.send_message(hl7_message, _retry_attempted=True)

            # Second timeout - throwing in the towel here!
            self._close_mllp_client()  # Close the connection after sending the message and receiving ACK
            raise TimeoutError(f"Failed to receive ACK within {self.ack_timeout_seconds} seconds after retrying:")

        except Exception as e:
            logger.error(f"Error occurred while sending message via MLLP: {e}")
            # Attempt to reset the connection for future messages
            self.mllp_client = self._close_and_create_new_mllp_client()
            raise ConnectionError(f"Connection error occurred while sending message via MLLP: {e}")

    def __enter__(self) -> "Hl7SenderClient":
        return self

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[Any]
    ) -> None:
        self.mllp_client.close()
