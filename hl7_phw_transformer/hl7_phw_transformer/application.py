import logging
import os

from event_logger_lib import EventLogger  # noqa: F401
from health_check_lib.health_check_server import TCPHealthCheckServer  # noqa: F401
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory  # noqa: F401

from .app_config import AppConfig  # noqa: F401
from .phw_transformer import PhwTransformer

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)


def main() -> None:
    transformer = PhwTransformer()
    transformer.run()


if __name__ == "__main__":
    main()
