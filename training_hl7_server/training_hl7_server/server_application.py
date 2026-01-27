"""Main server application for the Training HL7 Server."""

import os
import signal
import sys
import threading

from hl7apy.mllp import MLLPServer  # type: ignore[import-untyped]

from training_hl7_server.message_handler import MessageHandler


class TrainingHl7ServerApplication:
    """
    The main application class for the Training HL7 Server.

    This class:
    1. Loads configuration from environment variables
    2. Sets up the MLLP server with message handlers
    3. Handles graceful shutdown on SIGINT/SIGTERM
    """

    def __init__(self) -> None:
        """Initialize the server application."""
        # ===================================================================
        # Load configuration from environment variables
        # ===================================================================
        # Environment variables allow us to configure the server without
        # changing code - useful for different environments (dev, test, prod)

        # HOST: The network interface to bind to
        # "0.0.0.0" means accept connections from any network interface
        # "localhost" would only accept connections from the same machine
        self.host = os.environ.get("HOST", "0.0.0.0")

        # PORT: The TCP port number to listen on
        # Each service needs a unique port number
        self.port = int(os.environ.get("PORT", "2575"))

        # HL7_VERSION: The expected HL7 version for incoming messages
        # We'll validate that messages match this version
        self.expected_version = os.environ.get("HL7_VERSION", "2.3.1")

        # ===================================================================
        # Server instance (will be set when the server starts)
        # ===================================================================
        self.server: MLLPServer | None = None
        self.server_thread: threading.Thread | None = None

        # ===================================================================
        # Set up signal handlers for graceful shutdown
        # ===================================================================
        # When the user presses Ctrl+C or the container is stopped,
        # we want to shut down gracefully instead of abruptly terminating

        # SIGINT: Signal sent when Ctrl+C is pressed
        signal.signal(signal.SIGINT, self._signal_handler)

        # SIGTERM: Signal sent when the process is asked to terminate
        # (e.g., by Docker when stopping a container)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: object) -> None:
        """
        Handle shutdown signals gracefully.

        This method is called when the process receives SIGINT or SIGTERM.

        Args:
            signum: The signal number that was received.
            frame: The current stack frame (not used here).
        """
        print(f"\nReceived signal {signum}, shutting down...")
        self.stop_server()
        sys.exit(0)

    def start_server(self) -> None:
        """
        Start the MLLP server and listen for connections.

        This method sets up the MLLP server with message handlers and
        begins listening for incoming HL7 messages. It blocks until
        the server is stopped.
        """
        # ===================================================================
        # Print startup information
        # ===================================================================
        print("=" * 60)
        print("TRAINING HL7 SERVER")
        print("=" * 60)
        print(f"Host: {self.host}")
        print(f"Port: {self.port}")
        print(f"Expected HL7 Version: {self.expected_version}")
        print("=" * 60)
        print("Waiting for HL7 messages...")
        print("Press Ctrl+C to stop the server")
        print()

        # ===================================================================
        # Define message handlers
        # ===================================================================
        # The handlers dictionary maps message types to handler classes.
        # Format: "MESSAGE_TYPE^TRIGGER_EVENT": (HandlerClass, *args)
        #
        # When a message with type "ADT^A31" is received, the server will:
        # 1. Create an instance of MessageHandler
        # 2. Pass the message and self.expected_version as arguments
        # 3. Call the handler's reply() method to get the ACK response

        handlers = {
            "ADT^A31": (MessageHandler, self.expected_version),
        }

        # ===================================================================
        # Create and start the MLLP server
        # ===================================================================
        # MLLPServer is a TCP server that implements the MLLP protocol
        # MLLP (Minimum Lower Layer Protocol) wraps HL7 messages for
        # transmission over TCP/IP networks

        self.server = MLLPServer(
            host=self.host,  # Network interface to bind to
            port=self.port,  # TCP port to listen on
            handlers=handlers,  # Message handlers dictionary
            timeout=10,  # Socket timeout in seconds
        )

        # ===================================================================
        # Start the server in a background thread
        # ===================================================================
        # Why use threading?
        # The MLLPServer.serve_forever() method blocks forever, which means
        # it would prevent the main thread from responding to signals like
        # Ctrl+C or SIGTERM. By running it in a daemon thread:
        # 1. The main thread stays responsive to shutdown signals
        # 2. The daemon thread automatically exits when main thread exits
        # 3. We can cleanly shut down the server before exiting

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True  # Thread will exit when main thread exits
        self.server_thread.start()

        print("✓ Server started successfully!")
        print()

        # ===================================================================
        # Keep the main thread alive
        # ===================================================================
        # The server runs in a background thread, so we need to prevent
        # the main thread from exiting. We use Event.wait() which blocks
        # until interrupted by a signal (Ctrl+C or SIGTERM)
        #
        # Why Event.wait()?
        # - It's a clean way to block indefinitely
        # - It's interruptible by KeyboardInterrupt (Ctrl+C)
        # - It doesn't consume CPU (unlike a while True loop)
        # - It releases the GIL, allowing other threads to run efficiently

        try:
            # Create an event that will never be set - this keeps us waiting forever
            stop_event = threading.Event()
            stop_event.wait()  # Block indefinitely until signal received
        except KeyboardInterrupt:
            # This gets raised when Ctrl+C is pressed
            print("\nKeyboard interrupt received")
            self.stop_server()

    def stop_server(self) -> None:
        """
        Stop the MLLP server.

        This method is called during graceful shutdown to cleanly stop
        the server and close all connections.
        """
        if self.server:
            print("Stopping server...")
            self.server.shutdown()
            self.server.server_close()
            print("Server stopped.")

        if self.server_thread:
            self.server_thread.join(timeout=5)
            print("Server thread cleaned up.")
