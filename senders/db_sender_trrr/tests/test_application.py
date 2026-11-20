from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from message_bus_lib.dead_letter import DeadLetterMessage

from db_sender_trrr import application
from db_sender_trrr.db_client import FatalDatabaseError, TransientDatabaseError
from db_sender_trrr.request_payload import MAPPING_MERGE, MAPPING_NHS_ID_UPDATE

NHS_ID_UPDATE = {"LIMSIdentifier": "ABC123", "NewIdentifier": "9876543210", "NewIdentifierAssigningAuthority": "NHS"}
MERGE = {
    "OldIdentifier": "OLD-001",
    "OldIdentifierAssigningAuthority": "WLIMS",
    "NewIdentifier": "LIMS-77",
    "NewIdentifierAssigningAuthority": "WLIMS",
}
PROPS = {
    b"CorrelationId": b"corr-1",
    b"WorkflowID": b"lims-to-hub",
    b"MessageControlId": b"MSG1",
    b"MessageType": b"A31",
}
MERGE_PROPS = {**PROPS, b"MessageType": b"A40"}


def _message(body: str, props: dict[bytes, bytes] | None = PROPS) -> SimpleNamespace:
    return SimpleNamespace(body=[body.encode("utf-8")], application_properties=props, raw_amqp_message=None)


def _config() -> MagicMock:
    config = MagicMock()
    config.db_stored_procedure = "dbo.spProcessResult"
    config.db_name = "Clinical_Results"
    return config


class TestProcessMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.db_client = MagicMock()
        self.event_logger = MagicMock()
        self.metric_sender = MagicMock()

    def _run(self, body: str, props: dict[bytes, bytes] | None = PROPS) -> bool:
        return application.process_message(
            _message(body, props), self.db_client, _config(), self.event_logger, self.metric_sender
        )

    def test_nhs_id_update_executes_stored_procedure_with_payload(self) -> None:
        self.assertTrue(self._run(json.dumps(NHS_ID_UPDATE)))

        self.db_client.execute_identifier_update.assert_called_once_with(NHS_ID_UPDATE)
        self.metric_sender.send_metric.assert_called_once()
        attributes = self.metric_sender.send_metric.call_args.kwargs["attributes"]
        self.assertEqual(attributes["request_type"], MAPPING_NHS_ID_UPDATE)
        self.assertEqual(attributes["stored_procedure"], "dbo.spProcessResult")

    def test_merge_executes_same_stored_procedure_with_payload(self) -> None:
        self.assertTrue(self._run(json.dumps(MERGE), MERGE_PROPS))

        self.db_client.execute_identifier_update.assert_called_once_with(MERGE)
        attributes = self.metric_sender.send_metric.call_args.kwargs["attributes"]
        self.assertEqual(attributes["request_type"], MAPPING_MERGE)

    def test_blank_unmapped_parameter_is_passed_through(self) -> None:
        payload = {**MERGE, "OldIdentifierAssigningAuthority": ""}

        self.assertTrue(self._run(json.dumps(payload), MERGE_PROPS))

        self.db_client.execute_identifier_update.assert_called_once_with(payload)

    def test_invalid_payload_is_dead_lettered_without_database_call(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self._run("MSH|^~\\&|LIMS|...")

        self.assertEqual(ctx.exception.reason, "InvalidPayload")
        self.db_client.execute_identifier_update.assert_not_called()
        self.event_logger.log_message_failed.assert_called_once()

    def test_mixed_request_shape_is_dead_lettered(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self._run(json.dumps({**NHS_ID_UPDATE, "OldIdentifier": "X"}), MERGE_PROPS)

        self.assertEqual(ctx.exception.reason, "InvalidPayload")
        self.db_client.execute_identifier_update.assert_not_called()

    def test_legacy_request_type_property_is_ignored(self) -> None:
        # The body decides the request type; a stray routing property from an older mapper changes nothing.
        self.assertTrue(self._run(json.dumps(MERGE), {**MERGE_PROPS, b"TrrrRequestType": b"NHS_ID_UPDATE"}))

        attributes = self.metric_sender.send_metric.call_args.kwargs["attributes"]
        self.assertEqual(attributes["request_type"], MAPPING_MERGE)

    def test_fatal_database_error_is_dead_lettered(self) -> None:
        self.db_client.execute_identifier_update.side_effect = FatalDatabaseError("duplicate", "23000", 2627)

        with self.assertRaises(DeadLetterMessage) as ctx:
            self._run(json.dumps(NHS_ID_UPDATE))

        self.assertEqual(ctx.exception.reason, "StoredProcedureExecutionFailed")

    def test_transient_database_error_returns_false_for_retry(self) -> None:
        self.db_client.execute_identifier_update.side_effect = TransientDatabaseError("link failure", "08S01", 0)

        self.assertFalse(self._run(json.dumps(NHS_ID_UPDATE)))

    def test_logging_failure_after_commit_still_completes_message(self) -> None:
        self.event_logger.log_message_processed.side_effect = RuntimeError("logging down")

        self.assertTrue(self._run(json.dumps(NHS_ID_UPDATE)))

    def test_event_logs_use_request_properties_and_never_the_payload(self) -> None:
        self._run(json.dumps(NHS_ID_UPDATE))

        received_content = self.event_logger.log_message_received.call_args.args[0]
        self.assertEqual(received_content, "MessageControlId=MSG1, MessageType=A31")
        for call in self.event_logger.method_calls:
            for arg in list(call.args) + list(call.kwargs.values()):
                self.assertNotIn("9876543210", str(arg))

    def test_missing_properties_still_process_and_log_as_unknown(self) -> None:
        # The request type comes from the body, so properties are only needed for logging.
        self.assertTrue(self._run(json.dumps(NHS_ID_UPDATE), props=None))

        self.db_client.execute_identifier_update.assert_called_once_with(NHS_ID_UPDATE)
        received_content = self.event_logger.log_message_received.call_args.args[0]
        self.assertEqual(received_content, "MessageControlId=UNKNOWN, MessageType=UNKNOWN")


if __name__ == "__main__":
    unittest.main()
