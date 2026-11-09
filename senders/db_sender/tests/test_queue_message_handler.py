import unittest
from unittest.mock import MagicMock

from db_sender.app_config import AppConfig
from db_sender.handlers.queue_message_handler import QueueMessageHandler
from db_sender.msh_extractor import MshInfo


class TestQueueMessageHandler(unittest.TestCase):

    def setUp(self) -> None:
        self.config = AppConfig(
            connection_string="Endpoint=sb://localhost;",
            service_bus_namespace=None,
            ingress_topic_name="local-inthub-wrrs-stmsg-outbound",
            ingress_subscription_name="local-inthub-wrrs-stmsg-sub",
            ingress_session_id="risp-to-wrrs",
            db_server="localhost",
            db_port=1433,
            db_name="DRS",
            db_stored_procedure="dbo.prQueueMessage",
            db_username="sa",
            db_password="Password123!",  # nosec B106
            db_encrypt="No",
            db_trust_server_certificate="Yes",
            db_connection_timeout=30,
            db_command_timeout=60,
            managed_identity_client_id=None,
            workflow_id="risp-to-wrrs",
            microservice_id="wrrs_stmsg_dbsender",
            health_board="SHARED",
            peer_service="WRRS",
            health_check_hostname=None,
            health_check_port=None,
            log_level="INFO",
            default_is_priority=1,
            max_batch_size=10,
            db_procedure_type="queue_message",
            source_system="328",
        )
        self.mock_db_client = MagicMock()
        self.handler = QueueMessageHandler(self.config)

    def test_handle_message_delegates_to_db_client(self) -> None:
        raw_msg = "<XML>payload</XML>"
        msh_info = MshInfo(msh_text="<MSH>", control_id="MSG1", message_type="ORU^R01")

        self.handler.handle_message(
            raw_msg,
            metadata={},
            msh_info=msh_info,
            db_client=self.mock_db_client,
        )

        self.mock_db_client.execute_stored_procedure.assert_called_once_with(
            raw_msg,
            is_priority=True,
        )


if __name__ == "__main__":
    unittest.main()
