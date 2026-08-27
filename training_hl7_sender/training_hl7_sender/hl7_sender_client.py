"""
=============================================================================
MLLP Client Wrapper - Week 3 Training
=============================================================================

This module provides a wrapper around the hl7 library's MLLPClient,
adding socket management, timeout handling, and context manager support.

IMPORTANT: hl7 vs hl7apy
------------------------
We use TWO different libraries:
- 'hl7' (python-hl7): Provides MLLPClient for sending messages over TCP
- 'hl7apy': Provides message parsing and manipulation

The 'hl7' library is simpler but only handles transport.

KEY CONCEPTS:
-------------
1. Socket State Checking: Before sending, we check if the socket is still open
2. Connection Management: Automatically reconnect if the socket is closed
3. Retry Logic: One automatic retry on timeout with a fresh connection
4. Context Manager: Ensures clean resource cleanup with 'with' statement
"""

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
    """
    Check if a socket connection is closed.

    This function uses select() to peek at the socket without blocking.
    If there's data to read but recv returns 0 bytes, the socket is closed.

    Args:
        sock: The socket to check

    Returns:
        True if socket is closed, False if still open
    """
    try:
        # Check if the socket is readable (may indicate data or EOF)
        readable, _, _ = select.select([sock], [], [], 0)
        if readable:
            # Peek at data without removing from buffer (MSG_PEEK)
            # If we get 0 bytes back, the connection is closed
            data = sock.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
            return len(data) == 0
        return False  # No data, but socket is fine
    except BlockingIOError:
        return False  # Socket is open and reading would block
    except ConnectionResetError:
        return True  # Socket was closed
    except Exception:
        logger.exception("Unexpected exception when checking if socket is closed")
        return False


class HL7SenderClient:
    """
    A wrapper around MLLPClient for sending HL7 messages.

    This class provides:
    - Automatic socket state checking before each send
    - Automatic reconnection if socket is closed
    - One automatic retry on timeout errors
    - Context manager support for clean resource cleanup

    Example:
        with HL7SenderClient("localhost", 2591, 30) as client:
            ack = client.send_message(hl7_message)
            print(f"Received ACK: {ack}")
    """

    def __init__(self, receiver_mllp_hostname: str, receiver_mllp_port: int, ack_timeout_seconds: int):
        """
        Initialize the HL7 sender client and establish connection.

        Args:
            receiver_mllp_hostname: Hostname of the MLLP receiver
            receiver_mllp_port: Port of the MLLP receiver
            ack_timeout_seconds: How long to wait for an ACK response
        """
        self.receiver_mllp_hostname = receiver_mllp_hostname
        self.receiver_mllp_port = receiver_mllp_port
        self.ack_timeout_seconds = ack_timeout_seconds

        # Create the MLLP client and establish connection
        self.mllp_client: MLLPClient = self._create_mllp_client()

    def _close_mllp_client(self) -> None:
        """Close the MLLP client socket safely."""
        try:
            self.mllp_client.close()
        except Exception as e:
            logger.error(f"Error closing socket: {e}")

    def _create_mllp_client(self) -> MLLPClient:
        """
        Create and configure an MLLPClient instance.

        The MLLPClient from the 'hl7' library handles:
        - TCP socket creation
        - MLLP framing (adding SB/EB/CR characters)
        - Sending and receiving

        Returns:
            A configured MLLPClient ready to send messages
        """
        # Create the client (this also connects to the server)
        mllp_client = MLLPClient(self.receiver_mllp_hostname, self.receiver_mllp_port)

        # Set the socket timeout for waiting for ACK responses
        mllp_client.socket.settimeout(self.ack_timeout_seconds)

        return mllp_client

    def _close_and_create_new_mllp_client(self) -> MLLPClient:
        """
        Close the current connection and create a new one.

        This is used when we detect a stale or broken connection.
        """
        self._close_mllp_client()
        return self._create_mllp_client()

    def send_message(self, message: str, _retry_attempted: bool = False) -> str:
        """
        Send an HL7 message and wait for ACK response.

        This method implements smart connection management:
        1. Checks if socket is closed before sending
        2. Automatically reconnects if needed
        3. Retries once on timeout with a fresh connection
        4. Raises TimeoutError or ConnectionError on failure

        Args:
            message: The HL7 message to send (as a string)
            _retry_attempted: Internal flag to prevent infinite retries

        Returns:
            The ACK response message (stripped of MLLP framing)

        Raises:
            TimeoutError: If no ACK received within timeout (after retry)
            ConnectionError: If connection fails
        """
        # Check if the socket connection is still alive
        if is_socket_closed(self.mllp_client.socket):
            logger.info("Creating new MLLP client connection (socket was closed)")
            self.mllp_client = self._close_and_create_new_mllp_client()

        try:
            # Send message and receive ACK
            # The MLLPClient.send_message() handles MLLP framing automatically
            ack_response = self.mllp_client.send_message(message).decode("utf-8")

            # Strip MLLP framing characters from the response
            stripped_response = ack_response.strip(ENCODING_CHARS)

            return stripped_response

        except socket.timeout:
            # The receiver didn't respond in time
            if not _retry_attempted:
                logger.warning("Socket timeout occurred, attempting retry with new connection...")
                self.mllp_client = self._close_and_create_new_mllp_client()
                return self.send_message(message, _retry_attempted=True)

            # Second timeout - give up
            self._close_mllp_client()
            raise TimeoutError(f"No ACK received within {self.ack_timeout_seconds} seconds")

        except Exception as e:
            # Some other error occurred - reconnect for next attempt
            logger.error(f"Error sending message: {e}")
            self.mllp_client = self._close_and_create_new_mllp_client()
            raise ConnectionError(f"Connection error while sending message: {e}")

    # =========================================================================
    # Context Manager Protocol
    # =========================================================================
    # These methods allow using the client with 'with' statement:
    #   with HL7SenderClient(...) as client:
    #       client.send_message(...)
    # This ensures the socket is properly closed even if an error occurs.

    def __enter__(self) -> "HL7SenderClient":
        """Enter the context manager (called at start of 'with' block)."""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """
        Exit the context manager (called at end of 'with' block).

        This ensures the socket is closed even if an exception occurred.
        """
        self.mllp_client.close()