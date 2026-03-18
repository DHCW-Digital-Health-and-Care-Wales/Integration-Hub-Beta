import logging
from typing import Any, Callable, List

from azure.servicebus import ServiceBusMessage
from azure.servicebus.exceptions import OperationTimeoutError
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory

from .app_config import AppConfig
from .db_client import DatabaseClient
from .replay_record import ReplayRecord
from .replay_status import ReplayStatus

logger = logging.getLogger(__name__)


class MessageReplayJob:
    """Orchestrates the replay of messages from SQL Server to Service Bus.

    Processes one ReplayBatchId per execution. Reads pending rows from the
    MessageReplayQueue table in configurable-sized batches, sends them to the priority
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

                self._send_to_service_bus_with_retry(sender_client, records, replay_ids)

                self._update_loaded_status_with_retry(replay_ids)
                logger.info("Batch %d: %d records marked as Loaded", batch_number, len(replay_ids))

        logger.info("Message replay job finished successfully")

    def _retry_once(self, operation: Callable[[], Any], description: str) -> Any:
        """Execute an operation with one retry on failure."""
        try:
            return operation()
        except Exception:
            logger.warning("First %s attempt failed, retrying...", description, exc_info=True)
            try:
                return operation()
            except Exception:
                logger.error("Second %s attempt failed", description, exc_info=True)
                raise

    def _fetch_batch_with_retry(self, replay_batch_id: str) -> List[ReplayRecord]:
        """Fetch with one retry on failure. Aborts on double failure."""
        return self._retry_once(
            lambda: self._db_client.fetch_batch(replay_batch_id, self._config.replay_batch_size),
            "fetch batch from database",
        )

    def _update_loaded_status_with_retry(self, replay_ids: List[int]) -> None:
        """Mark records as Loaded with one retry on failure. Aborts on double failure."""
        self._retry_once(
            lambda: self._db_client.update_statuses(replay_ids, ReplayStatus.LOADED),
            "mark batch as Loaded in database",
        )

    def _send_to_service_bus_with_retry(
        self,
        sender_client: MessageSenderClient,
        records: List[ReplayRecord],
        replay_ids: List[int],
    ) -> None:
        """Send to Service Bus with one retry on failure. Marks batch as Failed on double failure.

        Error-specific behaviour:
        - ValueError (single message too large): unrecoverable — skip retry.
        - OperationTimeoutError: broker outcome unknown, messages may already be
          on the queue. Retry anyway, but warn about potential duplicates.
        - All other exceptions: transient — retry once normally.
        """
        try:
            self._send_batch_to_service_bus(sender_client, records)
            return
        except ValueError:
            logger.error(
                "Message exceeds Service Bus size limit, marking batch as Failed",
                exc_info=True,
            )
            try:
                self._db_client.update_statuses(replay_ids, ReplayStatus.FAILED)
            except Exception:
                logger.warning("Failed to mark batch as Failed in database", exc_info=True)
            raise
        except OperationTimeoutError:
            logger.warning(
                "Send timed out — broker outcome is unknown, messages may already "
                "be on the queue. Retrying, which may produce duplicates.",
                exc_info=True,
            )
        except Exception:
            logger.warning(
                "First send batch to Service Bus attempt failed, retrying...",
                exc_info=True,
            )

        # Retry — only reached when first attempt raised OperationTimeoutError or Exception
        try:
            self._send_batch_to_service_bus(sender_client, records)
        except Exception:
            logger.error(
                "Retry of send batch to Service Bus failed, marking batch as Failed",
                exc_info=True,
            )
            try:
                self._db_client.update_statuses(replay_ids, ReplayStatus.FAILED)
            except Exception:
                logger.warning("Failed to mark batch as Failed in database", exc_info=True)
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
