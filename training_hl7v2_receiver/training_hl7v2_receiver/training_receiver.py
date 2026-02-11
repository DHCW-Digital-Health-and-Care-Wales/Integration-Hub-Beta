"""Main server application for the Training HL7 Server."""

import signal
import sys
import threading

from hl7apy.mllp import MLLPServer

# WEEK 2 ADDITION: Import Service Bus components from shared_libs
# These are used to publish validated HL7 messages to Azure Service Bus queues
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from training_hl7v2_receiver.app_config import AppConfig
from training_hl7v2_receiver.error_handler import ErrorHandler
from training_hl7v2_receiver.message_handler import MessageHandler


class TrainingHl7v2ReceiverApplication:
    """
    The main application class for the Training HL7 Server.

    This class:
    1. Loads configuration from environment variables (EXERCISE 1)
    2. Sets up the MLLP server with message handlers
    3. Registers handlers for multiple message types (EXERCISE 3)
    4. Includes a fallback error handler (EXERCISE 2)
    5. Handles graceful shutdown on SIGINT/SIGTERM

    EXERCISE SOLUTIONS INTEGRATED HERE:
    ----------------------------------
    - Exercise 1: Uses AppConfig class for centralized config management
    - Exercise 2: ErrorHandler registered with "ERR" key
    - Exercise 3: ADT^A28 and ADT^A40 added to handlers dictionary
    - Exercise 4: allowed_senders passed to MessageHandler from AppConfig
    """

    def __init__(self) -> None:
        """Initialize the server application."""
        # =====================================================================
        # EXERCISE 1 SOLUTION: Load configuration using AppConfig
        # =====================================================================
        # Instead of reading environment variables directly throughout the code,
        # we load all configuration into a single AppConfig object.
        # This pattern provides:
        # - Centralized configuration management
        # - Type safety and validation
        # - Easy testing (can mock the config object)
        # - Clear documentation of all config options
        #
        # Production Reference:
        # See hl7_server/hl7_server/app_config.py and how it's used in
        # hl7_server_application.py start_server() method.

        self.config = AppConfig.read_env_config()

        # =====================================================================
        # WEEK 2 ADDITION: Service Bus sender client
        # =====================================================================
        # This will be initialized in start_server() if Service Bus is configured
        # The sender_client is used to publish validated HL7 messages to a queue
        self.sender_client: MessageSenderClient | None = None

        # =====================================================================
        # Server instance (will be set when the server starts)
        # =====================================================================
        self.server: MLLPServer | None = None
        self.server_thread: threading.Thread | None = None

        # =====================================================================
        # Set up signal handlers for graceful shutdown
        # =====================================================================
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

        This method demonstrates all 4 exercise solutions:
        - Exercise 1: Config loaded from AppConfig in __init__
        - Exercise 2: ErrorHandler registered with "ERR" key
        - Exercise 3: ADT^A28 and ADT^A40 handlers added
        - Exercise 4: allowed_senders passed to MessageHandler
        """
        # =====================================================================
        # Print startup information
        # =====================================================================
        # Show configuration so operators can verify settings are correct
        print("=" * 60)
        print("TRAINING HL7 SERVER")
        print("=" * 60)
        print(f"Host: {self.config.host}")
        print(f"Port: {self.config.port}")
        print(f"Expected HL7 Version: {self.config.hl7_version or '(any)'}")
        print(f"Allowed Senders: {self.config.allowed_senders or '(any)'}")

        # =====================================================================
        # WEEK 2 ADDITION: Initialize Service Bus sender
        # =====================================================================
        # If Service Bus is configured, create a sender client to publish
        # validated messages to the egress queue. The transformer component
        # will read from this queue.
        if self.config.connection_string and self.config.egress_queue_name:
            print("-" * 60)
            print("SERVICE BUS INTEGRATION ENABLED (Week 2)")
            print(f"Egress Queue: {self.config.egress_queue_name}")
            print(f"Session ID: {self.config.egress_session_id or '(none)'}")

            # Create connection configuration for Service Bus
            # Uses connection string for local emulator, namespace for Azure
            client_config = ConnectionConfig(
                connection_string=self.config.connection_string,
                service_bus_namespace=None,  # Not used when connection_string is set
            )

            # Create the factory that builds Service Bus clients
            factory = ServiceBusClientFactory(client_config)

            # Create a queue sender client for publishing messages
            # The session_id ensures ordered processing in session-enabled queues
            self.sender_client = factory.create_queue_sender_client(
                queue_name=self.config.egress_queue_name,
                session_id=self.config.egress_session_id,
            )
            print("✓ Service Bus sender initialized")
        else:
            print("-" * 60)
            print("SERVICE BUS INTEGRATION DISABLED")
            print("(Set SERVICE_BUS_CONNECTION_STRING and EGRESS_QUEUE_NAME to enable)")

        print("=" * 60)
        print("Waiting for HL7 messages...")
        print("Press Ctrl+C to stop the server")
        print()

        # =====================================================================
        # Define message handlers (EXERCISES 2, 3, 4)
        # =====================================================================
        # The handlers dictionary maps message types to handler classes.
        # Format: "MESSAGE_TYPE^TRIGGER_EVENT": (HandlerClass, *args)
        #
        # When a message with type "ADT^A31" is received, the server will:
        # 1. Create an instance of MessageHandler
        # 2. Pass the message and handler arguments
        # 3. Call the handler's reply() method to get the ACK response
        #
        # EXERCISE 4 SOLUTION:
        # The allowed_senders is passed from config to the MessageHandler.
        # This enables validation of sending applications (MSH-3).

        # Arguments passed to MessageHandler for each message type
        # Tuple format: (HandlerClass, arg1, arg2, ...)
        # MessageHandler expects: (message, expected_version, allowed_senders, sender_client)
        # Note: 'message' is passed automatically by the MLLP library
        #
        # WEEK 2 ADDITION: sender_client is now passed to publish messages to Service Bus
        message_handler_args = (
            MessageHandler,
            self.config.hl7_version,  # expected_version parameter
            self.config.allowed_senders,  # EXERCISE 4: allowed_senders parameter
            self.sender_client,  # WEEK 2: Service Bus sender client (can be None)
        )

        handlers = {
            # =================================================================
            # EXERCISE 3 SOLUTION: Support multiple message types
            # =================================================================
            # Register the same handler for different ADT message types.
            # Each of these message types will be processed identically.
            #
            # Production Reference:
            # See training_hl7v2_receiver/training_hl7v2_receiver/training_receiver.py handlers dict
            # which supports even more message types including PIMS and Chemocare
            # specific formats like "ADT^A31^ADT_A05" (with message structure)
            "ADT^A05": message_handler_args,  # Added A05 support
            "ADT^A31": message_handler_args,
            "ADT^A28": message_handler_args,  # EXERCISE 3: Added A28 support
            "ADT^A40": message_handler_args,  # EXERCISE 3: Added A40 support
            "MDM^T01": message_handler_args,  # Added MDM^T01 support
            "MDM^T02": message_handler_args,  # Added MDM^T02 support
            "ORU^R01": message_handler_args,  # Added ORU^R01 support
            "OMG^O19": message_handler_args,  # Added OMG^O19 support
            "SIU^S12": message_handler_args,  # Added SIU^S12 support
            "SIU^S14": message_handler_args,  # Added SIU^S14 support
            "SIU^S15": message_handler_args,  # Added SIU^S15 support
            "SIU^S26": message_handler_args,  # Added SIU^S26 support
            # =================================================================
            # EXERCISE 2 SOLUTION: Fallback error handler
            # =================================================================
            # The special key "ERR" registers a fallback handler that catches
            # any message type not explicitly listed above.
            #
            # When to use an error handler:
            # - A message type arrives that we don't have a handler for
            # - The message cannot be parsed
            # - An exception occurs during processing
            #
            # Without this handler, unsupported messages would cause the
            # connection to drop without sending a response. With it, we
            # can return a proper error ACK (NACK) to the sender.
            #
            # Production Reference:
            # See training_hl7v2_receiver/training_hl7v2_receiver/error_handler.py and how it's registered
            # in training_hl7v2_receiver/training_hl7v2_receiver/training_receiver.py with the event_logger for audit trails.
            "ERR": (ErrorHandler,),  # EXERCISE 2: Fallback error handler
        }

        # =====================================================================
        # Create and start the MLLP server
        # =====================================================================
        # MLLPServer is a TCP server that implements the MLLP protocol
        # MLLP (Minimum Lower Layer Protocol) wraps HL7 messages for
        # transmission over TCP/IP networks

        self.server = MLLPServer(
            host=self.config.host,  # Network interface to bind to
            port=self.config.port,  # TCP port to listen on
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

        # =====================================================================
        # WEEK 2 ADDITION: Close the Service Bus sender client
        # =====================================================================
        if self.sender_client:
            print("Closing Service Bus sender...")
            self.sender_client.close()
            print("Service Bus sender closed.")
