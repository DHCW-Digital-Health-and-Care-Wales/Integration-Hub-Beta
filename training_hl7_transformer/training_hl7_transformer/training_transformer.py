"""
Training HL7 Transformer
========================

This module contains the main transformer class that orchestrates message
transformation. It demonstrates the transformation pattern used throughout
the Integration Hub project.

LEARNING OBJECTIVES:
-------------------
1. Understand the transformer's role in the message pipeline
2. Learn how to apply segment mappers to transform messages
3. See how the ingress -> transform -> egress flow works

THE TRANSFORMATION PIPELINE:
---------------------------
1. HL7 Server receives raw HL7 message over TCP/MLLP
2. Server validates and publishes to INGRESS queue
3. Transformer reads from INGRESS queue
4. Transformer parses, transforms, and builds new message
5. Transformer publishes to EGRESS queue
6. Next component (e.g., Sender) reads from EGRESS queue

WHY TRANSFORM MESSAGES?
----------------------
Different healthcare systems use different:
- Field formats (date/time, identifiers)
- Application codes (MSH-3, MSH-5)
- Message structures (segment ordering)
- HL7 versions (2.3.1 vs 2.5)

Transformers act as adapters between systems, ensuring messages
are compatible with the receiving system's expectations.

PRODUCTION REFERENCE:
--------------------
See hl7_phw_transformer/hl7_phw_transformer/phw_transformer.py
for a production transformer that inherits from BaseTransformer.
"""

import os
import signal
import sys
from collections.abc import Callable

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message
from hl7apy.parser import parse_message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from training_hl7_transformer.app_config import TransformerConfig

# ===========================================================================
# WEEK 2 EXERCISE 2 & 3 SOLUTIONS: Import additional mappers
# ===========================================================================
from training_hl7_transformer.mappers.evn_mapper import map_evn
from training_hl7_transformer.mappers.msh_mapper import map_msh
from training_hl7_transformer.mappers.pid_mapper import map_pid


class TrainingTransformer:
    """
    A minimal HL7 transformer for training purposes.

    This class demonstrates the core transformer pattern without the
    complexity of the production BaseTransformer class. It:

    1. Connects to Service Bus ingress and egress queues
    2. Receives messages from the ingress queue
    3. Parses and transforms each message
    4. Publishes transformed messages to the egress queue
    5. Acknowledges (completes) processed messages

    Unlike production transformers, this class:
    - Uses print() instead of structured logging
    - Doesn't include health checks or metrics
    - Has a simpler message processing loop

    Attributes:
        name: Display name for logging
        config_path: Path to config.ini file
        running: Flag to control the main loop
    """

    def __init__(self) -> None:
        """Initialize the transformer."""
        self.name = "Training"

        # Path to config.ini in the same directory as this module
        self.config_path = os.path.join(os.path.dirname(__file__), "config.ini")

        # Flag to control the main processing loop
        # Set to False when shutdown signal is received
        self.running = True

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals gracefully."""
        print(f"\nReceived signal {signum}, shutting down...")
        self.running = False
        # Force exit after signal to break out of receive_messages blocking call
        sys.exit(0)

    def transform_message(self, hl7_msg: Message) -> Message:
        """
        Transform an HL7 message.

        This is the core transformation logic. It creates a new HL7 message
        and applies mappers to transform each segment.

        STRETCH EXERCISE 2: Add PID segment mapping
        -------------------------------------------
        Currently, we only transform the MSH segment. Try adding a mapper
        for the PID (Patient Identification) segment:

        1. Create training_hl7_transformer/mappers/pid_mapper.py
        2. Import and call map_pid(hl7_msg, new_message) here
        3. See hl7_phw_transformer/mappers/pid_mapper.py for reference

        Args:
            hl7_msg: The parsed original HL7 message.

        Returns:
            A new Message object with transformations applied.
        """
        # Create a new HL7 message with version 2.3.1
        # This ensures consistent output regardless of input version
        new_message = Message(version="2.3.1")

        # Apply MSH mapper to transform the Message Header segment
        # WEEK 2 EXERCISE 1 SOLUTION: MSH mapper now includes datetime transformation
        _ = map_msh(hl7_msg, new_message)  # Result used for logging inside the mapper

        # =====================================================================
        # WEEK 2 EXERCISE 2 SOLUTION: Add EVN segment mapping
        # =====================================================================
        # The EVN (Event Type) segment contains event information.
        # We use a try/except block because EVN might not exist in all messages.
        try:
            _ = map_evn(hl7_msg, new_message)
        except AttributeError:
            print("EVN segment not present in original message (skipping)")

        # =====================================================================
        # WEEK 2 EXERCISE 3 SOLUTION: Add PID segment mapping
        # =====================================================================
        # The PID (Patient Identification) segment contains patient demographics.
        # This mapper also transforms the patient name to uppercase.
        try:
            _ = map_pid(hl7_msg, new_message)
        except AttributeError:
            print("PID segment not present in original message (skipping)")

        return new_message

    def _create_message_processor(
        self, sender_client: MessageSenderClient, config: TransformerConfig
    ) -> Callable[[ServiceBusMessage], bool]:
        """
        Create a message processor callback function.

        PRODUCTION PATTERN EXPLANATION FOR BEGINNERS:
        ---------------------------------------------
        This method demonstrates a key pattern used in all production transformers:
        creating a "closure" - a nested function that has access to variables from
        its parent scope.

        Why use this pattern?
        1. The message processor needs access to both sender_client AND config
        2. But the MessageReceiverClient only passes the message to the callback
        3. By defining process_message inside this method, it can "capture"
           sender_client and config from the outer scope
        4. This is cleaner than using class instance variables

        In production code (transformer_base_lib/run_transformer.py), this same
        pattern is used - message_processor is defined as a nested function inside
        run_transformer_app(), giving it access to sender_client, event_logger,
        transformer, and config.

        Args:
            sender_client: The sender client for publishing transformed messages.
            config: The loaded configuration (passed in, not an instance variable).

        Returns:
            A callback function that processes a single message.
        """

        def process_message(message: ServiceBusMessage) -> bool:
            """
            Process a single message from the queue.

            IMPORTANT: This nested function has access to 'config' and 'sender_client'
            from the parent scope - this is called a "closure" in Python.
            Even though these aren't passed as parameters, they're captured from
            the _create_message_processor method above.

            This callback:
            1. Extracts the HL7 content from the Service Bus message
            2. Parses it into an HL7 Message object
            3. Applies transformations
            4. Publishes to egress queue
            5. Returns True if successful, False if an error occurred

            The MessageReceiverClient will:
            - Complete (remove) the message if this returns True
            - Abandon (requeue) the message if this returns False

            Args:
                message: The Service Bus message containing HL7 content.

            Returns:
                True if transformation succeeded, False otherwise.
            """
            try:
                # Log that we picked up a message from the queue
                # Note: 'config' is accessible here even though it's not a parameter!
                print(f"\n>>> PICKED UP MESSAGE from queue: {config.ingress_queue_name}")

                # Get the raw message body as string
                raw_body = str(message)

                print("-" * 60)
                print("PROCESSING MESSAGE FROM QUEUE")
                print("-" * 60)

                # Parse the HL7 message
                # find_groups=False simplifies parsing (no group structures)
                hl7_msg = parse_message(raw_body, find_groups=False)

                # Extract key identifiers for logging
                message_control_id = hl7_msg.msh.msh_10.value
                message_type = hl7_msg.msh.msh_9.to_er7()

                print(f"Message Control ID: {message_control_id}")
                print(f"Message Type: {message_type}")

                # Apply transformations
                transformed_msg = self.transform_message(hl7_msg)
                transformed_body = transformed_msg.to_er7()

                print(f"✓ Transformation complete for {message_control_id}")

                # =============================================================
                # PUBLISH transformed message to egress queue
                # =============================================================
                # Again, 'config' is accessible from the closure
                print(f">>> PUBLISHING to queue: {config.egress_queue_name}")
                try:
                    sender_client.send_text_message(transformed_body)
                    print(f"✓ Published to egress: {message_control_id}")
                except Exception as send_error:
                    # If send fails (e.g., connection timeout), log and re-raise
                    # The message will be abandoned and retried
                    print(f"✗ Error publishing to egress: {send_error}")
                    raise

                # Return True = message will be completed (removed from queue)
                return True

            except Exception as e:
                print(f"✗ Error processing message: {e}")
                # Return False = message will be abandoned (requeued for retry)
                return False

        return process_message

    def run(self) -> None:
        """
        Main entry point for the transformer.

        PRODUCTION PATTERN EXPLANATION FOR BEGINNERS:
        ---------------------------------------------
        This method follows the exact pattern used in transformer_base_lib/run_transformer.py:

        1. Load config as a LOCAL VARIABLE (not an instance variable)
           - This is key! In production, config lives in run_transformer_app() scope
           - We don't store it as self.config because we don't need it after run()

        2. Create Service Bus clients with the config
           - ConnectionConfig wraps connection settings
           - ServiceBusClientFactory creates sender and receiver clients

        3. Define message_processor as a nested function
           - The nested function can access 'config' from this method's scope
           - This is cleaner than passing config through self

        4. Enter the message processing loop
           - Receive messages in batches
           - Process each with the callback
           - Loop continues until shutdown signal

        The loop continues until self.running is set to False
        (by the signal handler) or an unrecoverable error occurs.
        """
        # =====================================================================
        # STEP 1: Load configuration as a LOCAL variable
        # =====================================================================
        # IMPORTANT: In production (transformer_base_lib/run_transformer.py),
        # config is loaded as a local variable in run_transformer_app().
        # It's NOT stored as an instance variable (self.config).
        # This means we don't need Optional types or type guards!
        print("=" * 60)
        print("TRAINING HL7 TRANSFORMER")
        print("=" * 60)
        print("Loading configuration...")

        config = TransformerConfig.from_env_and_config_file(self.config_path)

        print(f"Ingress Queue: {config.ingress_queue_name}")
        print(f"Ingress Session ID: {config.ingress_session_id or '(none)'}")
        print(f"Egress Queue: {config.egress_queue_name}")
        print(f"Egress Session ID: {config.egress_session_id or '(none)'}")
        print(f"Max Batch Size: {config.max_batch_size}")
        print("=" * 60)

        # =====================================================================
        # STEP 2: Create Service Bus clients
        # =====================================================================
        # PRODUCTION PATTERN: This matches transformer_base_lib/run_transformer.py
        # exactly. We create:
        # 1. ConnectionConfig - holds connection settings
        # 2. ServiceBusClientFactory - creates sender and receiver clients
        # 3. sender_client - publishes transformed messages to egress queue
        # 4. receiver_client - receives messages from ingress queue
        # LOCAL: Uses connection_string for Service Bus emulator
        # AZURE: Uses service_bus_namespace with managed identity

        connection_config = ConnectionConfig(
            connection_string=config.connection_string,
            service_bus_namespace=config.service_bus_namespace,
        )

        factory = ServiceBusClientFactory(connection_config)

        # Create sender for egress queue (where transformed messages go)
        sender_client = factory.create_queue_sender_client(
            queue_name=config.egress_queue_name,
            session_id=config.egress_session_id,
        )

        # Create receiver for ingress queue (where raw messages come from)
        receiver_client = factory.create_message_receiver_client(
            queue_name=config.ingress_queue_name, session_id=config.ingress_session_id
        )

        print("✓ Service Bus clients initialized")
        print("Waiting for messages...")
        print("Press Ctrl+C to stop")
        print()

        # =====================================================================
        # STEP 3: Main processing loop (PRODUCTION PATTERN)
        # =====================================================================
        # PRODUCTION PATTERN: This matches transformer_base_lib/run_transformer.py
        # The MessageReceiverClient uses a callback pattern:
        # - We create a function (message_processor) that processes one message
        # - The function returns True for success, False for failure
        # - The client automatically handles completion/abandonment
        # - The client also handles retry delays and session locking
        #
        # KEY POINT: message_processor is created by _create_message_processor()
        # as a nested function that has access to both sender_client AND config
        # from this scope. This is the "closure" pattern.

        try:
            # Create the message processor callback
            # We pass both sender_client and config so the nested function can access them
            message_processor = self._create_message_processor(sender_client, config)

            with sender_client:
                # Note: receiver_client creates new connections on each receive_messages() call
                # so we don't need it in the with block. Only sender needs to stay open.
                while self.running:
                    # The receive_messages method:
                    # 1. Receives up to num_of_messages from the queue
                    # 2. Calls message_processor for each message
                    # 3. Completes messages when processor returns True
                    # 4. Abandons messages when processor returns False
                    # 5. Handles retry delays and session locking errors
                    #
                    # Note: This call creates and destroys receiver connections internally
                    # so idle timeout won't affect the receiver
                    receiver_client.receive_messages(
                        num_of_messages=config.max_batch_size,
                        message_processor=message_processor,
                    )

        except Exception as e:
            print(f"Fatal error in transformer: {e}")
            sys.exit(1)

        print("Transformer stopped.")
