import unittest
from unittest.mock import MagicMock

from message_bus_lib.dead_letter import DeadLetterMessage

from db_sender.app_config import AppConfig
from db_sender.application import process_message
from db_sender.db_client import FatalDatabaseError, TransientDatabaseError


class TestApplication(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig(
            connection_string="Endpoint=sb://localhost;",
            service_bus_namespace=None,
            ingress_topic_name="test-topic",
            ingress_subscription_name="test-sub",
            ingress_session_id="test-session",
            db_server="localhost",
            db_port=1433,
            db_name="DRS",
            db_stored_procedure="dbo.prQueueMessage",
            db_username="sa",
            db_password="pwd",  # nosec B106
            db_encrypt="No",
            db_trust_server_certificate="Yes",
            db_connection_timeout=30,
            db_command_timeout=60,
            managed_identity_client_id=None,
            workflow_id="risp-to-wrrs",
            microservice_id="wrrs_db_sender",
            health_board="SHARED",
            peer_service="WRRS",
            health_check_hostname="127.0.0.1",
            health_check_port=9000,
            log_level="INFO",
            default_is_priority=0,
            max_batch_size=10,
        )
        self.mock_db_client = MagicMock()
        self.mock_event_logger = MagicMock()
        self.mock_metric_sender = MagicMock()

    def _create_mock_message(self, body_str: str) -> MagicMock:
        mock_msg = MagicMock()
        mock_msg.body = [body_str.encode("utf-8")]
        mock_msg.application_properties = {
            b"CorrelationId": b"test-corr-id-123",
            b"WorkflowId": b"risp-to-wrrs",
        }
        return mock_msg

    def test_process_message_success(self) -> None:
        msg_body = (
            "<ADT_A39><MSH><MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2><MSG.3>ADT_A39</MSG.3></MSH.9>"
            "<MSH.10><MSH.10.1>MSG-123</MSH.10.1></MSH.10></MSH>"
            "<PID><PID.5><XPN.1><FN.1>SECRET_PATIENT</FN.1></XPN.1></PID.5></PID></ADT_A39>"
        )
        mock_message = self._create_mock_message(msg_body)

        result = process_message(
            mock_message,
            self.mock_db_client,
            self.config,
            self.mock_event_logger,
            self.mock_metric_sender,
        )

        self.assertTrue(result)
        self.mock_db_client.execute_stored_procedure.assert_called_once_with(msg_body, is_priority=False)
        self.mock_metric_sender.send_metric.assert_called_once_with(
            "messages_sent", 1, attributes={"database": "DRS", "stored_procedure": "dbo.prQueueMessage"}
        )
        # Check Information Governance: verify logged text contains MSH but never SECRET_PATIENT
        rec_call_args = self.mock_event_logger.log_message_received.call_args[0]
        self.assertNotIn("SECRET_PATIENT", rec_call_args[0])
        self.assertIn("MSH", rec_call_args[0])

        proc_call_args = self.mock_event_logger.log_message_processed.call_args[0]
        self.assertNotIn("SECRET_PATIENT", proc_call_args[0])
        self.assertIn("MSH", proc_call_args[0])

    def test_process_message_fatal_error(self) -> None:
        mock_message = self._create_mock_message("MSH|^~\\&|349|349|||20261022||ADT^A40|CTRL1|P|2.5\rPID|1||999")
        self.mock_db_client.execute_stored_procedure.side_effect = FatalDatabaseError(
            "Could not find stored procedure 'dbo.prQueueMessage'", sql_state="42000", error_code=2812
        )

        with self.assertRaises(DeadLetterMessage) as ctx:
            process_message(
                mock_message,
                self.mock_db_client,
                self.config,
                self.mock_event_logger,
                self.mock_metric_sender,
            )

        self.assertEqual(ctx.exception.reason, "StoredProcedureExecutionFailed")
        self.assertIn("Could not find stored procedure", ctx.exception.description)
        self.mock_event_logger.log_message_failed.assert_called_once()

    def test_process_message_transient_error(self) -> None:
        mock_message = self._create_mock_message("MSH|^~\\&|349|349|||20261022||ADT^A40|CTRL1|P|2.5\rPID|1||999")
        self.mock_db_client.execute_stored_procedure.side_effect = TransientDatabaseError(
            "Query timeout expired", sql_state="HYT00", error_code=0
        )

        result = process_message(
            mock_message,
            self.mock_db_client,
            self.config,
            self.mock_event_logger,
            self.mock_metric_sender,
        )

        self.assertFalse(result)
        self.mock_event_logger.log_message_failed.assert_not_called()

    def test_process_message_unexpected_error(self) -> None:
        mock_message = self._create_mock_message("MSH|^~\\&|349|349|||20261022||ADT^A40|CTRL1|P|2.5\rPID|1||999")
        self.mock_db_client.execute_stored_procedure.side_effect = RuntimeError("Unknown failure")

        result = process_message(
            mock_message,
            self.mock_db_client,
            self.config,
            self.mock_event_logger,
            self.mock_metric_sender,
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
