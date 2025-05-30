from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.identity import DefaultAzureCredential
from typing import Optional
import logging
from messaging.ServiceBusConfig import ServiceBusConfig


class ServiceBusMessageSender:
    def __init__(self):
        self.config = ServiceBusConfig.from_env()
        self._client: Optional[ServiceBusClient] = None

        logging.info(f"Service Bus config - Queue: {self.config.queue_name}, "
                    f"Is local: {self.config.is_local_setup()}")

    def send_message(self, message_content: str) -> None:
        try:
            if self.config.is_local_setup():
                logging.info("Using connection string authentication")
                client = ServiceBusClient.from_connection_string(
                    conn_str=self.config.connection_string
                )
            else:
                # Use namespace for cloud environment
                fully_qualified_namespace = f"{self.config.namespace}.servicebus.windows.net"
                logging.info(f"Using managed identity with namespace: {fully_qualified_namespace}")
                credential = DefaultAzureCredential()
                client = ServiceBusClient(
                    fully_qualified_namespace=fully_qualified_namespace,
                    credential=credential
                )

            with client:
                with client.get_queue_sender(queue_name=self.config.queue_name) as sender:
                    message = ServiceBusMessage(message_content)
                    sender.send_messages(message)
                    logging.info(f"Successfully sent message to queue: {self.config.queue_name}")
        except Exception as e:
            logging.error(f"Failed to send message to Service Bus: {e}")
            raise