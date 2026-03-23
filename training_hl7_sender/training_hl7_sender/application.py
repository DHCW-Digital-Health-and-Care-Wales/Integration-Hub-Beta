"""
=============================================================================
Main Application - Week 3 Training
=============================================================================

This is the entry point for the Training HL7 Sender. It orchestrates:
1. Configuration loading
2. Service Bus connection setup
3. MLLP client initialization
4. The main message processing loop
5. Graceful shutdown handling


PRODUCTION REFERENCE:
--------------------
The production hl7_sender/application.py includes:
- Message throttling (rate limiting)
- Metrics and audit logging
- Batch size calculation based on throttle settings
"""

import logging
import os

from azure.servicebus import ServiceBusMessage
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager

from training_hl7_sender.ack_processor import get_ack_result
from training_hl7_sender.app_config import AppConfig
from training_hl7_sender.hl7_sender_client import HL7SenderClient

# =============================================================================
# Logging Setup
# =============================================================================
# Configure logging based on environment variable
# Default to INFO level for training visibility
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Reduce Azure SDK logging noise
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================
# Maximum number of messages to receive in one batch
# Larger batches are more efficient but use more memory
MAX_BATCH_SIZE = 10


def main() -> None:
    """
    Main entry point for the Training HL7 Sender.

    This function:
    1. Sets up the ProcessorManager for signal handling
    2. Reads configuration from environment variables
    3. Creates Service Bus and MLLP clients
    4. Runs the message processing loop until shutdown

    The function uses context managers (with statements) to ensure
    all resources are properly cleaned up on exit.
    """
    print("=" * 60)
    print("Training HL7 Sender - Week 3")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # Step 1: Set up signal handling for graceful shutdown
    # -------------------------------------------------------------------------
    # ProcessorManager registers handlers for SIGINT (Ctrl+C) and SIGTERM.
    # When either signal is received, processor_manager.is_running becomes False.
    processor_manager = ProcessorManager()
    print("Signal handlers registered (SIGINT, SIGTERM)")

    # -------------------------------------------------------------------------
    # Step 2: Load configuration from environment
    # -------------------------------------------------------------------------
    app_config = AppConfig.read_env_config()
    print("Configuration loaded:")
    print(f"    Queue: {app_config.ingress_queue_name}")
    print(f"    Session: {app_config.ingress_session_id}")
    print(f"    Destination: {app_config.receiver_mllp_hostname}:{app_config.receiver_mllp_port}")

    # -------------------------------------------------------------------------
    # Step 3: Create Service Bus client factory
    # -------------------------------------------------------------------------
    # The factory creates receiver and sender clients with proper authentication.
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)
    print("Service Bus client factory created")

    # -------------------------------------------------------------------------
    # Step 4: Create clients and run the main loop
    # -------------------------------------------------------------------------
    # Using 'with' statements ensures proper cleanup even if errors occur.
    with (
        # Create a receiver client for the ingress queue
        factory.create_message_receiver_client(
            app_config.ingress_queue_name,
            app_config.ingress_session_id,
        ) as receiver_client,
        # Create the MLLP sender client
        HL7SenderClient(
            app_config.receiver_mllp_hostname,
            app_config.receiver_mllp_port,
            app_config.ack_timeout_seconds,
        ) as hl7_sender_client,
    ):
        print("=" * 60)
        print("Sender started - waiting for messages...")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        logger.info("Processor started.")

        # Main processing loop
        while processor_manager.is_running:
            # Receive messages from the queue and process them
            # The callback function is called for each message
            receiver_client.receive_messages(
                MAX_BATCH_SIZE,
                lambda message: _process_message(message, hl7_sender_client),
            )

    # Context managers have cleaned up, we're done
    print("=" * 60)
    print("Sender stopped gracefully")
    print("=" * 60)


def _process_message(message: ServiceBusMessage, hl7_sender_client: HL7SenderClient) -> bool:
    """
    Process a single message from the queue.

    This callback function is called by the receiver for each message.
    It must return True if the message was processed successfully (complete it),
    or False if processing failed (abandon it for retry).

    Args:
        message: The Service Bus message containing the HL7 content
        hl7_sender_client: The MLLP client for sending

    Returns:
        True if message was sent and ACK was positive
        False if sending failed or ACK was negative
    """
    # Decode the message body from bytes to string
    message_body = b"".join(message.body).decode("utf-8")

    # Log that we received a message (for visibility)
    # Extract message control ID for logging
    try:
        # Quick extraction of MSH-10 (message control ID) for logging
        msh_line = message_body.split("\r")[0] if "\r" in message_body else message_body.split("\n")[0]
        parts = msh_line.split("|")
        control_id = parts[9] if len(parts) > 9 else "unknown"
    except Exception:
        control_id = "unknown"

    print(f"Picked up message from queue '{hl7_sender_client.receiver_mllp_hostname}':")
    print(f"    Control ID: {control_id}")
    logger.info(f"Received message from queue, Control ID: {control_id}")

    try:
        # Send the message via MLLP
        print(
            f"Sending via MLLP to {hl7_sender_client.receiver_mllp_hostname}:{hl7_sender_client.receiver_mllp_port}..."
        )
        ack_response = hl7_sender_client.send_message(message_body)

        # Validate the ACK response
        ack_success = get_ack_result(ack_response)

        if ack_success:
            logger.info("Message sent successfully, ACK validated")
            return True
        else:
            logger.warning("Message sent but ACK indicates failure")
            return False

    except TimeoutError as e:
        print(f"Timeout: {e}")
        logger.error(f"Timeout sending message: {e}")
        return False

    except ConnectionError as e:
        print(f"Connection error: {e}")
        logger.error(f"Connection error: {e}")
        return False

    except Exception as e:
        print(f"Unexpected error: {e}")
        logger.exception("Unexpected error processing message")
        return False


if __name__ == "__main__":
    main()
