import os
from typing import Optional

class ServiceBusConfig:
    @staticmethod
    def get_queue_name() -> str:
        queue_name = os.getenv('QUEUE_NAME')
        if not queue_name:
            raise ValueError("QUEUE_NAME environment variable is not set")
        return queue_name

    @staticmethod
    def get_connection_string() -> Optional[str]:
        return os.getenv('QUEUE_CONNECTION_STRING')

    @staticmethod
    def get_namespace() -> Optional[str]:
        return os.getenv('SERVICE_BUS_NAMESPACE')