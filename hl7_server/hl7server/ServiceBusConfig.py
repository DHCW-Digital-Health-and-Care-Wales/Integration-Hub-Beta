from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class ServiceBusConfig:
    queue_name: str
    connection_string: Optional[str] = None
    namespace: Optional[str] = None

    @classmethod
    def from_env(cls) -> 'ServiceBusConfig':
        queue_name = os.getenv("QUEUE_NAME")
        if not queue_name:
            raise ValueError("QUEUE_NAME environment variable is required")

        connection_string = os.getenv("QUEUE_CONNECTION_STRING")
        namespace = os.getenv("SERVICE_BUS_NAMESPACE")

        if not connection_string and not namespace:
            raise ValueError(
                "Either QUEUE_CONNECTION_STRING or SERVICE_BUS_NAMESPACE must be provided"
            )

        return cls(
            queue_name=queue_name,
            connection_string=connection_string,
            namespace=namespace
        )

    def is_local_setup(self) -> bool:
        return self.connection_string is not None