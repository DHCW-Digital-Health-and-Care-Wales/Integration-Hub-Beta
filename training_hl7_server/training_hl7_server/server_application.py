import signal
import sys
import threading

from hl7apy.mllp import MLLPServer  # type: ignore[import-untyped]

from training_hl7_server.app_config import AppConfig
from training_hl7_server.error_handler import ErrorHandler
from training_hl7_server.message_handler import MessageHandler


class TrainingHl7ServerApplication:
    """Main server application for the Training HL7 Server"""

    def __init__(self) -> None:
        """entry point for the Training HL7 Server application."""
        self.app_config = AppConfig.read_env_config()
        self.server: MLLPServer | None = None
        self.server_thread: threading.Thread | None = None

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: object) -> None:
        print(f"\nReceived signal {signum}, shutting down...")
        self.stop_server()
        sys.exit(0)

    def start_server(self) -> None:
        """start_server starts the MLLP HL7 server."""
        # ===================================================================
        # Print startup information
        # ===================================================================
        print("=" * 60)
        print("TRAINING HL7 SERVER")
        print("=" * 60)
        print(f"Host: {self.app_config.host}")
        print(f"Port: {self.app_config.port}")
        print(f"Expected HL7 Version: {self.app_config.hl7_version or 'Any'}")
        print(f"Allowed Senders: {self.app_config.allowed_senders or 'Any'}")
        print("=" * 60)
        print("Waiting for HL7 messages...")
        print("Press Ctrl+C to stop the server")

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
            "ADT^A31": (MessageHandler, self.app_config.hl7_version),
            "ERR": (ErrorHandler),
        }

        # ===================================================================
        # Create and start the MLLP server
        # ===================================================================
        # MLLPServer is a TCP server that implements the MLLP protocol
        # MLLP (Minimum Lower Layer Protocol) wraps HL7 messages for
        # transmission over TCP/IP networks

        self.server = MLLPServer(
            host=self.app_config.host,  # Network interface to bind to
            port=self.app_config.port,  # TCP port to listen on
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

        print("=" * 60)
        print("✓ Server started successfully!")
        print("=" * 60)

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
        """Stop the MLLP server."""
        if self.server:
            print("Stopping server...")
            self.server.shutdown()
            self.server.server_close()
            print("Server stopped.")

        if self.server_thread:
            self.server_thread.join(timeout=5)
            print("Server thread cleaned up.")
