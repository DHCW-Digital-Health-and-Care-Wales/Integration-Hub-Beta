"""
Training HL7 Verification
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

from email.mime import message
import os
import signal
import sys

from azure.servicebus import ServiceBusMessage
from hl7apy.core import Message
from hl7apy.parser import parse_message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from training_hl7_verification.app_config import VerificationConfig
from lxml import etree
#from training_hl7_transformer.mappers.msh_mapper import map_msh
#from training_hl7_transformer.mappers.pid_mapper import map_pid


class TrainingVerification:
    """
    A minimal HL7 verification for training purposes.

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
        config: TransformerConfig instance
        running: Flag to control the main loop
    """

    def __init__(self) -> None:
        """Initialize the verification."""
        self.name = "Training"

        # Path to config.ini in the same directory as this module
        self.config_path = os.path.join(os.path.dirname(__file__), "config.ini")

        # Will be loaded when run() is called
        self.config: VerificationConfig | None = None

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
 
        # Create a new HL7 message with version 2.3.1
        # This ensures consistent output regardless of input version
        new_message = Message(version="2.5.1")
        # Read the custom property we set in _route_message
    
        # Apply MSH mapper to transform the Message Header segment
        #_ = map_msh(hl7_msg, new_message)  # Result used for logging inside the mapper
        
        # Apply PID mapper
        """
        try:
            _ = map_pid(hl7_msg, new_message)
        except AttributeError:
            print("PID segment not present in original message (skipping)")
        """
        # =====================================================================
        # STRETCH EXERCISE 2: Add more segment mappers here
        # =====================================================================
        # Example:
        # from training_hl7_transformer.mappers.pid_mapper import map_pid
        # pid_details = map_pid(hl7_msg, new_message)

        return new_message

    

    def _create_message_processor(self, sender_client: MessageSenderClient):
        """
        Create a message processor callback function.

        This is the production pattern used by all transformers.
        The MessageReceiverClient calls this function for each message,
        and handles completion/abandonment based on the return value.

        Args:
            sender_client: The sender client for publishing transformed messages.

        Returns:
            A callback function that processes a single message.
        """

        def process_message(message: ServiceBusMessage) -> bool:
            """
            Process a single message from the queue.

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
            print("-" * 60)
            print("PROCESSING MESSAGE FROM QUEUE")
            print("-" * 60)
            
            try:
                # Log that we picked up a message from the queue
                print(f"\n>>> PICKED UP MESSAGE from queue: {self.config.ingress_queue_name}")

                # Get the raw message body as string
                raw_body = str(message)

                # Parse the HL7 message
                # find_groups=False simplifies parsing (no group structures)
                hl7_msg = parse_message(raw_body, find_groups=False)

                # Extract key identifiers for logging
                message_control_id = hl7_msg.msh.msh_10.value
                message_type = hl7_msg.msh.msh_9.to_er7()

                print(f"Message Control ID: {message_control_id}")
                print(f"Message Type: {message_type}")

                # Debug: Print all application properties
                subject = "DEFAULT_QUEUE"
                if message.application_properties:
                    print(f"Application properties: {dict(message.application_properties)}")
                    # Handle both bytes and string keys/values
                    subject = message.application_properties.get(b"subject", b"DEFAULT_QUEUE")
                    if isinstance(subject, bytes):
                        subject = subject.decode("utf-8")
                else:
                    print("No application properties found on message")
                
                if subject == "ADT_QUEUE":
                    print("✓ Detected subject: ADT_QUEUE")
                elif subject == "MDM_QUEUE":
                    print("✓ Detected subject: MDM_QUEUE")
                elif subject == "ORDERS_QUEUE":
                    print("✓ Detected subject: ORDERS_QUEUE")
                elif subject == "RESULTS_QUEUE":
                    print("✓ Detected subject: RESULTS_QUEUE")
                    # Do strict schema validation with the customised ORU_R01 xsd schema for training
                    schema_path = os.path.join(
                        os.path.dirname(__file__),
                        "schemas",
                        "oru_r01_training.xsd"
                    )

                    try:
                        # Load and validate against XSD schema
                        # hl7apy provides XML conversion through its serialization methods
                        schema_doc = etree.parse(schema_path)
                        schema = etree.XMLSchema(schema_doc)
                        
                        # Get XML representation of the HL7 message
                        # Use hl7apy's built-in XML generation
                        xml_str = hl7_msg.serialize(encoding='utf-8', pretty_print=True)
                        xml_doc = etree.fromstring(xml_str)
                        
                        # Validate against schema
                        if schema.validate(xml_doc):
                            print(f"✓ Message validation passed for {message_control_id}")
                        else:
                            # Print detailed validation errors
                            error_log = schema.error_log
                            print(f"✗ Message validation failed for {message_control_id}")
                            for error in error_log:
                                print(f"  - {error}")
                            return False
                            
                    except FileNotFoundError:
                        print(f"✗ Schema file not found: {schema_path}")
                        return False
                    except etree.XMLSyntaxError as xml_error:
                        print(f"✗ XML parsing error: {xml_error}")
                        return False
                    except Exception as schema_error:
                        print(f"✗ Schema validation error: {schema_error}")
                        return False
                else:
                    print(f"✓ Detected subject: {subject} (Non Defined QUEUE)")

                # Apply transformations
                transformed_msg = self.transform_message(hl7_msg)
                transformed_body = transformed_msg.to_er7()

                print(f"✓ Transformation complete for {message_control_id}")

                # =============================================================
                # PUBLISH transformed message to egress queue
                # =============================================================
                print(f">>> PUBLISHING to queue: {self.config.egress_queue_name}")
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
        Run the transformer main loop.

        This method:
        1. Loads configuration from environment and config file
        2. Creates Service Bus clients for ingress and egress queues
        3. Enters a loop that receives and processes messages
        4. Publishes transformed messages and completes originals
        5. Exits gracefully on shutdown signal

        The loop continues until self.running is set to False
        (by the signal handler) or an unrecoverable error occurs.
        """
        # =====================================================================
        # STEP 1: Load configuration
        # =====================================================================
        print("=" * 60)
        print("TRAINING HL7 VERIFICATION")
        print("=" * 60)
        print("Loading configuration...")

        self.config = VerificationConfig.from_env_and_config_file(self.config_path)

        print(f"Ingress Queue: {self.config.ingress_queue_name}")
        print(f"Ingress Session ID: {self.config.ingress_session_id or '(none)'}")
        print(f"Egress Queue: {self.config.egress_queue_name}")
        print(f"Egress Session ID: {self.config.egress_session_id or '(none)'}")
        print(f"Max Batch Size: {self.config.max_batch_size}")
        print("=" * 60)

        # =====================================================================
        # STEP 2: Create Service Bus clients
        # =====================================================================
        # This is the production pattern used by all transformers:
        # 1. ConnectionConfig holds connection settings
        # 2. ServiceBusClientFactory creates sender and receiver clients
        # 3. MessageSenderClient wraps the Azure SDK sender
        # 4. MessageReceiverClient wraps the Azure SDK receiver

        client_config = ConnectionConfig(
            connection_string=self.config.connection_string,
            service_bus_namespace=None,  # Not used when connection_string is set
        )
        factory = ServiceBusClientFactory(client_config)

        # Create sender client for egress queue
        sender_client = factory.create_queue_sender_client(
            queue_name=self.config.egress_queue_name,
            session_id=self.config.egress_session_id,
        )

        # Create receiver client for ingress queue
        receiver_client = factory.create_message_receiver_client(
            queue_name=self.config.ingress_queue_name,
            session_id=self.config.ingress_session_id,
        )

        print("✓ Service Bus clients initialized")
        print("Waiting for messages...")
        print("Press Ctrl+C to stop")
        print()

        # =====================================================================
        # STEP 3: Main processing loop (PRODUCTION PATTERN)
        # =====================================================================
        # The MessageReceiverClient uses a callback pattern:
        # - We provide a function that processes one message
        # - The function returns True for success, False for failure
        # - The client automatically handles completion/abandonment
        # - The client also handles retry delays and session locking

        try:
            # Create the message processor callback with access to sender_client
            message_processor = self._create_message_processor(sender_client)

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
                        num_of_messages=self.config.max_batch_size,
                        message_processor=message_processor,
                    )

        except Exception as e:
            print(f"Fatal error in verification: {e}")
            sys.exit(1)

        print("Training verification stopped.")
