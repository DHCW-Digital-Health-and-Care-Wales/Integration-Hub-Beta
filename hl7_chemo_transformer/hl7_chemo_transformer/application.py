import logging
import os
from typing import Callable

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from hl7apy.core import Message
from message_bus_lib.message_sender_client import MessageSenderClient
from transformer_base_lib import run_transformer_app
from transformer_base_lib.processing import process_message as base_process_message

from .chemocare_transformer import transform_chemocare_message

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
logger = logging.getLogger(__name__)


def main() -> None:
    config_path = os.path.join(os.path.dirname(__file__), "config.ini")

    def process(
        message: ServiceBusMessage,
        sender: MessageSenderClient,
        event_logger: EventLogger,
        transform_fn: Callable[[Message], Message],
    ) -> bool:
        def processed_audit_text_builder(_msg: Message) -> str:
            sending_app = _get_sending_app(_msg)
            return f"Chemocare transformation applied for SENDING_APP: {sending_app}"

        return base_process_message(
            message=message,
            sender_client=sender,
            event_logger=event_logger,
            transform=transform_fn,
            transformer_display_name="Chemocare",
            received_audit_text="Message received for Chemocare transformation",
            processed_audit_text_builder=processed_audit_text_builder,
            failed_audit_text="Chemocare transformation failed",
        )

    run_transformer_app(
        transformer_display_name="Chemocare",
        transform=transform_chemocare_message,
        process_message_fn=process,
        config_path=config_path,
    )


def _get_sending_app(hl7_msg: Message) -> str:
    try:
        return hl7_msg.msh.msh_3.msh_3_1.value
    except (AttributeError, IndexError):
        return "UNKNOWN"


if __name__ == "__main__":
    main()


def _process_message(
    message: ServiceBusMessage,
    sender_client: MessageSenderClient,
    event_logger: EventLogger,
) -> bool:
    def processed_audit_text_builder(_msg: Message) -> str:
        sending_app = _get_sending_app(_msg)
        return f"Chemocare transformation applied for SENDING_APP: {sending_app}"

    return base_process_message(
        message=message,
        sender_client=sender_client,
        event_logger=event_logger,
        transform=transform_chemocare_message,
        transformer_display_name="Chemocare",
        received_audit_text="Message received for Chemocare transformation",
        processed_audit_text_builder=processed_audit_text_builder,
        failed_audit_text="Chemocare transformation failed",
    )
