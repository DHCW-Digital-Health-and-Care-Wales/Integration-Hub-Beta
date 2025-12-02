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
        # First check: Try to get socket error state using SO_ERROR
        # This will return non-zero if there's a pending error (e.g., connection reset)
        error_code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if error_code != 0:
            logger.warning(f"Socket has error state: error_code={error_code}")
            return True

        # Second check: Use select to see if socket is readable
        # A timeout of 0 makes this non-blocking
        readable, _, exceptional = select.select([sock], [], [sock], 0)

        # If socket is in exceptional condition, it's likely closed or errored
        if exceptional:
            logger.warning("Socket is in exceptional condition")
            return True

        # If socket is readable, try to peek at the data
        if readable:
            # Try to peek at data without removing it from the buffer
            # MSG_PEEK: peek at incoming data without removing it
            # MSG_DONTWAIT: non-blocking operation
            data = sock.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
            if len(data) == 0:
                # recv returning 0 bytes means the connection was closed gracefully (EOF)
                logger.warning("Socket is closed: recv returned 0 bytes (EOF detected)")
                return True
            else:
                # There's data waiting to be read, but we shouldn't have any in this context
                # This might indicate leftover data from a previous message or an unexpected state
                logger.warning(f"Socket has unexpected data: peeked {len(data)} bytes - treating as closed")
                return True

        # No errors detected, socket appears healthy
        logger.debug("Socket is open: no errors detected")
        return False

    except BlockingIOError:
        # This is normal for non-blocking sockets with no data available
        logger.debug("Socket is open: BlockingIOError indicates socket is operational")
        return False
    except (ConnectionResetError, BrokenPipeError, OSError) as e:
        # These exceptions indicate the socket is definitely closed or broken
        logger.warning(f"Socket is closed: {type(e).__name__} - {e}")
        return True
    except Exception as e:
        # Unexpected exception - log it and assume socket might be closed to be safe
        logger.error(f"Unexpected exception checking socket state: {type(e).__name__} - {e}")
        return True  # Changed from False to True to be more conservative


class HL7SenderClient:

    def __init__(self, receiver_mllp_hostname: str, receiver_mllp_port: int, ack_timeout_seconds: int):
        self.mllp_client = MLLPClient(receiver_mllp_hostname, receiver_mllp_port)
        self.receiver_mllp_hostname = receiver_mllp_hostname
        self.receiver_mllp_port = receiver_mllp_port
        self.ack_timeout_seconds = ack_timeout_seconds

    def send_message(self, message: str) -> str:
        logger.debug("Checking if socket is closed before sending message")
        if is_socket_closed(self.mllp_client.socket):
            logger.info("Socket is closed, creating new MLLP client connection")
            try:
                self.mllp_client.close()
            except Exception as e:
                logger.warning(f"Error closing old socket (expected): {e}")
            self.mllp_client = MLLPClient(self.receiver_mllp_hostname, self.receiver_mllp_port)
            logger.info("New MLLP client connection established successfully")
        else:
            logger.debug("Socket is open, reusing existing connection")

        self.mllp_client.socket.settimeout(self.ack_timeout_seconds)

        try:
            logger.debug(f"Sending HL7 message (length: {len(message)} chars)")
            ack_response = self.mllp_client.send_message(message).decode('utf-8')
            stripped_response = ack_response.strip(ENCODING_CHARS)
            logger.debug(f"Received ACK response: {stripped_response[:100]}...")
            return stripped_response
        except socket.timeout as e:
            # Timeout means the connection might be stale - close it so next send creates a new one
            logger.error(f"No ACK received within {self.ack_timeout_seconds} seconds: {e}")
            logger.info("Closing socket due to timeout to force reconnection on next send")
            try:
                self.mllp_client.close()
            except Exception as close_error:
                logger.warning(f"Error closing socket after timeout: {close_error}")
            raise TimeoutError(f"No ACK received within {self.ack_timeout_seconds} seconds, {e}")
        except (ConnectionError, BrokenPipeError, OSError) as e:
            # Connection errors indicate socket is broken - close it
            logger.error(f"Connection error while sending message: {type(e).__name__} - {e}")
            logger.info("Closing socket due to connection error to force reconnection on next send")
            try:
                self.mllp_client.close()
            except Exception as close_error:
                logger.warning(f"Error closing socket after connection error: {close_error}")
            raise ConnectionError(f"Connection error while sending message: {e}")
        except Exception as e:
            # Unexpected error - log details and close socket to be safe
            logger.error(f"Unexpected error while sending message: {type(e).__name__} - {e}")
            logger.info("Closing socket due to unexpected error")
            try:
                self.mllp_client.close()
            except Exception as close_error:
                logger.warning(f"Error closing socket after unexpected error: {close_error}")
            raise

    def __enter__(self) -> "HL7SenderClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        self.mllp_client.close()
