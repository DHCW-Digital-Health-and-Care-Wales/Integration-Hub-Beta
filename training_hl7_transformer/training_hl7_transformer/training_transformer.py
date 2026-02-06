import os
import signal
import sys
from collections.abc import Callable

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message  # type: ignore
from hl7apy.parser import parse_message  # type: ignore
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from training_hl7_transformer.app_config import TransformerConfig

from .mappers.evn_mapper import map_evn
from .mappers.msh_mapper import map_msh
from .mappers.pid_mapper import map_pid


class TrainingTransformer:
    def __init__(self) -> None:
        """Initialize the TrainingTransformer."""
        self.name = "Training"

        # config.ini path
        self.config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        print(f"Loading configuration from: {self.config_path}")

        # for mainloop control
        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals gracefully."""
        print(f"\nReceived signal {signum}, shutting down...")
        self.running = False
        # Force exit after signal to break out of receive_messages blocking call
        sys.exit(0)

    def transform_message(self, hl7_msg: Message) -> Message:
        """Transform the incoming HL7 message.

        Args:
            hl7_msg (Message): The incoming HL7 message.

        Returns:
            Message: The transformed HL7 message.
        """
        print("Starting Message Transformation.")

        new_msg = Message(version="2.3.1")

        trans_datetime = map_msh(hl7_msg, new_msg)
        if trans_datetime:
            print(f"Transformed MSH Datetime details: {trans_datetime}")

        trans_evn = map_evn(hl7_msg, new_msg)
        if trans_evn:
            print(f"Transformed EVN details: {trans_evn}")

        trans_pid = map_pid(hl7_msg, new_msg)
        if trans_pid:
            print(f"Transformed PID details: {trans_pid}\n")

        print("✓ Message Transformation Complete.\n")

        print(f"Transformed Message:\n{new_msg.to_er7()}\n")

        return new_msg

    def _create_message_processor(
        self,
        sender_client: MessageSenderClient,
        config: TransformerConfig,
    ) -> Callable[[ServiceBusMessage], bool]:
        """Create a message processor function.

        Args:
            sender_client (MessageSenderClient): The message sender client.
            config (TransformerConfig): The transformer configuration.

        Returns:
            Callable[[ServiceBusMessage], bool]: The message processor function.
        """

        def process_message(message: ServiceBusMessage) -> bool:
            """Process an incoming Service Bus message.
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
                message (ServiceBusMessage): The incoming Service Bus message.

            Returns:
                bool: True if processing was successful, False otherwise.
            """
            try:
                # Note: 'config' is accessible here even though it's not a parameter!
                print(f"\n>>> PICKED UP MESSAGE from queue: {config.ingress_queue_name}")

                raw_body = str(message)
                print("Raw message body:\n",raw_body)

                print("\n" + "=" * 60 + "\nPROCESSING MESSAGE FROM QUEUE\n" + "=" * 60)

                # Parse the HL7 message
                # find_groups=False simplifies parsing (no group structures)
                hl7_msg = parse_message(raw_body, find_groups=False)

                # Extract key identifiers for logging
                message_control_id = hl7_msg.msh.msh_10.value  # type: ignore
                message_type = hl7_msg.msh.msh_9.to_er7()  # type: ignore

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
                    print(f"✓ Published transformed message {message_control_id} to {config.egress_queue_name}")

                except Exception as send_error:
                    # If send fails (e.g., connection timeout), log and re-raise
                    # The message will be abandoned and retried
                    print(f"\n✗ Error publishing to egress: {send_error}")
                    raise

                # Return True = message will be completed (removed from queue)
                return True

            except Exception as e:
                print(f"\n✗ Error processing message: {e}")
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
