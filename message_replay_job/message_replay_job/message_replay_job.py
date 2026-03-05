import logging
from typing import List

from azure.servicebus import ServiceBusMessage
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from .app_config import AppConfig
from .db_client import DatabaseClient
from .replay_record import ReplayRecord

logger = logging.getLogger(__name__)


class MessageReplayJob:
    """Orchestrates the replay of messages from SQL Server to Service Bus.

    Processes one ReplayBatchId per execution. Reads pending rows from the
    MessageReplayQueue table in batches of 1000, sends them to the priority
    Service Bus queue, and updates their status.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._db_client = DatabaseClient(
            sql_server=config.sql_server,
            sql_database=config.sql_database,
            sql_username=config.sql_username,
            sql_password=config.sql_password,
            sql_encrypt=config.sql_encrypt,
            sql_trust_server_certificate=config.sql_trust_server_certificate,
            managed_identity_client_id=config.managed_identity_client_id,
        )

    def run(self) -> None:
        """Execute the replay job to completion.

        Loops through all pending replay records for the configured batch ID,
        sending them to Service Bus and updating statuses. Raises on fatal errors.
        """
        sb_config = ConnectionConfig(
            connection_string=self._config.connection_string,
            service_bus_namespace=self._config.service_bus_namespace,
        )
        factory = ServiceBusClientFactory(sb_config)
        sender_client = factory.create_queue_sender_client(queue_name=self._config.priority_queue_name)

        with self._db_client, factory, sender_client:
            batch_number = 0
            while True:
                batch_number += 1
                logger.info(
                    "Processing batch %d for replay batch %s",
                    batch_number,
                    self._config.replay_batch_id,
                )

                records = self._fetch_batch_with_retry(self._config.replay_batch_id)

                if not records:
                    logger.info("No more pending records found. Job complete.")
                    break

                replay_ids = [r.replay_id for r in records]
                logger.info(
                    "Fetched %d records (ReplayId range: %d-%d)",
                    len(records),
                    replay_ids[0],
                    replay_ids[-1],
                )

                self._send_with_retry(sender_client, records, replay_ids)

                # Mark as Loaded — no retry, abort on failure
                try:
                    self._db_client.update_statuses(replay_ids, "Loaded")
                    logger.info("Batch %d: %d records marked as Loaded", batch_number, len(replay_ids))
                except Exception:
                    logger.error("Failed to mark records as Loaded, aborting", exc_info=True)
                    raise

        logger.info("Message replay job finished successfully")

    def _fetch_batch_with_retry(self, replay_batch_id: str) -> List[ReplayRecord]:
        """Fetch with one retry on failure. Aborts on double failure."""
        try:
            return self._db_client.fetch_batch(replay_batch_id)
        except Exception:
            logger.warning("First fetch attempt failed, retrying...", exc_info=True)
            try:
                return self._db_client.fetch_batch(replay_batch_id)
            except Exception:
                logger.error("Second fetch attempt failed, aborting job", exc_info=True)
                raise

    def _send_with_retry(
        self,
        sender_client: MessageSenderClient,
        records: List[ReplayRecord],
        replay_ids: List[int],
    ) -> None:
        """Send with one retry on failure. Marks batch as Failed on double failure."""
        try:
            self._send_batch_to_service_bus(sender_client, records)
        except Exception:
            logger.warning("First send attempt failed, retrying...", exc_info=True)
            try:
                self._send_batch_to_service_bus(sender_client, records)
            except Exception:
                logger.error("Second send attempt failed, marking batch as Failed", exc_info=True)
                self._db_client.update_statuses(replay_ids, "Failed")
                raise

    @staticmethod
    def _build_messages(records: List[ReplayRecord]) -> List[ServiceBusMessage]:
        """Build ServiceBusMessage objects from replay records."""
        return [
            ServiceBusMessage(
                body=record.raw_payload,
                application_properties={
                    "CorrelationId": record.correlation_id,
                    "ReplayId": str(record.replay_id),
                    "MessageId": str(record.message_id),
                },
            )
            for record in records
        ]

    def _send_batch_to_service_bus(self, sender_client: MessageSenderClient, records: List[ReplayRecord]) -> None:
        """Build messages from records and delegate batch sending to the shared lib."""
        messages = self._build_messages(records)
        sender_client.send_message_batch(messages)


__all__ = ["MessageReplayJob"]
