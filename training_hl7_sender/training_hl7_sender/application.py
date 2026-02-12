import logging
import os
import time

from azure.servicebus import ServiceBusMessage
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager

from training_hl7_sender.ack_processor import get_ack_result
from training_hl7_sender.app_config import AppConfig

from .hl7_sender_client import Hl7SenderClient

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Reduce Azure SDK logging verbosity
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)

logger = logging.getLogger(__name__)

# CONST
MAX_BATCH_SIZE = 10
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1


def main() -> None:
    print("=" * 60 + "\nStarting HL7 Sender Application...\n" + "=" * 60)

    processor_manager = ProcessorManager()
    print("Signal handlers registered (SIGINT, SIGTERM). Setting up Service Bus client...")

    app_config = AppConfig.read_env_config()
    print("Configuration loaded from environment variables.")
    print(f"      Queue Name: {app_config.ingress_queue_name}")
    print(f"      Session: {app_config.ingress_session_id}")
    print(f"      Destination: {app_config.receiver_mllp_hostname}:{app_config.receiver_mllp_port}")

    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)
    print("Service Bus client factory created.")

    with (
        # Create a receiver client for the ingress queue
        factory.create_message_receiver_client(
            app_config.ingress_queue_name,
            session_id=app_config.ingress_session_id,
        ) as receiver_client,
        # Create MLLP sender client
        Hl7SenderClient(
            app_config.receiver_mllp_hostname,
            app_config.receiver_mllp_port,
            app_config.ack_timeout_seconds,
        ) as hl7_sender_client,
    ):
        print("=" * 60 + "\nSender started...\nEntering main processing loop...\nWaiting for messages...\n" + "=" * 60)
        logger.info("Sender started. Waiting for messages...")

        while processor_manager.is_running:
            receiver_client.receive_messages(
                MAX_BATCH_SIZE,
                lambda message: _process_message(message, hl7_sender_client),
            )

    print("=" * 60 + "\nSender stopped.\n" + "=" * 60)
    logger.info("Sender stopped.")


def _process_message(message: ServiceBusMessage, hl7_sender_client: Hl7SenderClient) -> bool:
    message_body = b"".join(message.body).decode("utf-8")

    try:
        msh_line = message.body.split("\r")[0] if "r" in message.body else message_body.split("\n")[0]
        parts = msh_line.split("|")
        control_id = parts[9] if len(parts) > 9 else "Unknown"
    except Exception as e:
        logger.warning(f"Failed to parse MSH segment for Control ID: {e}")
        control_id = "Unknown"

    print(f"Picked up message from queue '{hl7_sender_client.receiver_mllp_hostname}':")
    print(f"  Control ID: {control_id}")
    logger.info(f"Processing message with Control ID: {control_id}")

    for attempt in range(0, RETRY_ATTEMPTS):
        print(f"Attempt {attempt + 1} of {RETRY_ATTEMPTS} to send message with Control ID {control_id}...")

        try:
            mllp_destination = f"{hl7_sender_client.receiver_mllp_hostname}:{hl7_sender_client.receiver_mllp_port}"
            print(f"  Sending message via MLLP to {mllp_destination}...")
            ack_response = hl7_sender_client.send_message(message_body)

            ack_success = get_ack_result(ack_response)

            if ack_success:
                print(f"  ACK received with status: {ack_success}. Completing message in Service Bus.")
                logger.info(f"Message with Control ID {control_id} processed successfully. ACK status: {ack_success}")
                return True
            # raise TimeoutError("Simulated timeout after successful ACK to trigger retry logic for testing purposes.")
            else:
                print(f"  ACK received with status: {ack_success} indicates failure.")
                logger.warning(
                    f"Message with Control ID {control_id} processed but ACK indicates "
                    f"failure. ACK status: {ack_success}"
                )
                return False

        except TimeoutError as e:
            print(f"  Timeout while waiting for ACK: {e}")
            logger.error(f"Timeout while waiting for ACK for message with Control ID {control_id}: {e}")
            # Retry
            print(f"  Retrying after {RETRY_DELAY_SECONDS} seconds...")
            time.sleep(RETRY_DELAY_SECONDS)

        except ConnectionError as e:
            print(f"  Connection error while sending message: {e}")
            logger.error(f"Connection error while sending message with Control ID {control_id}: {e}")
            # Retry
            print(f"  Retrying after {RETRY_DELAY_SECONDS} seconds...")
            time.sleep(RETRY_DELAY_SECONDS)

        except Exception as e:
            print(f"  Unexpected error while processing message: {e}")
            logger.error(f"Unexpected error while processing message with Control ID {control_id}: {e}")
            return False

    # After exhausting retries, print/log failure and return False
    print(
        f"Failed to process message with Control ID {control_id} after "
        f"{RETRY_ATTEMPTS} attempts. Abandoning message."
    )
    logger.error(f"Failed to process message with Control ID {control_id} after {RETRY_ATTEMPTS} attempts.")
    return False


if __name__ == "__main__":
    main()
