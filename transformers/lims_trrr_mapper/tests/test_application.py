from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from message_bus_lib.dead_letter import DeadLetterMessage

from lims_trrr_mapper import application
from lims_trrr_mapper.identifier_mapper import MAPPING_MERGE, MAPPING_NHS_ID_UPDATE

A31 = (
    "MSH|^~\\&|LIMS|LIMS|TRRR|TRRR|20250101010101||ADT^A31^ADT_A05|MSG-A31|P|2.5\r"
    "PID|1||ABC123^^^328^PI~9876543210^^^NHS^NH||Doe^John\r"
)
A40_WITH_NHS = (
    "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG1|P|2.5\r"
    "PID|1||LIMS-77^^^WLIMS^PI~9876543210^^^NHS^NH||Doe^John\r"
    "MRG|OLD-001^^^WLIMS^PI\r"
)
A40_WITHOUT_NHS = (
    "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG2|P|2.5\r"
    "PID|1||LIMS-77^^^WLIMS^PI||Doe^John\r"
    "MRG|OLD-001^^^WLIMS^PI\r"
)
A40_WITHOUT_MRG = (
    "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG3|P|2.5\r"
    "PID|1||LIMS-77^^^WLIMS^PI~9876543210^^^NHS^NH||Doe^John\r"
)

# Service Bus delivers application property keys/values as bytes; mirror that here.
INCOMING_PROPS = {
    b"CorrelationId": b"corr-1",
    b"WorkflowID": b"lims-to-hub",
    b"SourceSystem": b"328",
    b"MessageReceivedAt": b"2025-01-01T01:01:01Z",
    b"MessageType": b"A40",
}


def _message(body: str, props: dict[bytes, bytes] | None = None) -> SimpleNamespace:
    return SimpleNamespace(body=[body.encode("utf-8")], application_properties=props, raw_amqp_message=None)


def _config(mapping_type: str) -> MagicMock:
    config = MagicMock()
    config.mapping_type = mapping_type
    config.egress_topic_name = "local-inthub-lims-trrr-mapped"
    return config


class TestProcessMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.sender = MagicMock()
        self.event_logger = MagicMock()

    def _run(self, body: str, mapping_type: str, props: dict[bytes, bytes] | None = None) -> bool:
        return application.process_message(
            _message(body, props),  # type: ignore[arg-type]
            self.sender,
            _config(mapping_type),
            self.event_logger,
        )

    def _published(self) -> tuple[dict[str, str], dict[str, str]]:
        self.sender.send_text_message.assert_called_once()
        call = self.sender.send_text_message.call_args
        return json.loads(call.args[0]), call.kwargs["custom_properties"]

    def test_nhs_id_update_publishes_stored_procedure_parameters_for_a31(self) -> None:
        self.assertTrue(self._run(A31, MAPPING_NHS_ID_UPDATE))

        payload, props = self._published()
        self.assertEqual(
            payload,
            {"LIMSIdentifier": "ABC123", "NewIdentifier": "9876543210", "NewIdentifierAssigningAuthority": "NHS"},
        )
        self.assertNotIn("TrrrRequestType", props)
        self.assertEqual(props["MessageControlId"], "MSG-A31")

    def test_nhs_id_update_forwards_incoming_tracking_properties(self) -> None:
        self._run(A40_WITH_NHS, MAPPING_NHS_ID_UPDATE, INCOMING_PROPS)

        _, props = self._published()
        self.assertEqual(props["CorrelationId"], "corr-1")
        self.assertEqual(props["WorkflowID"], "lims-to-hub")
        self.assertEqual(props["SourceSystem"], "328")
        # The upstream MessageType (trigger event) is kept, not replaced by the full MSH-9 value.
        self.assertEqual(props["MessageType"], "A40")
        self.assertEqual(props["MessageControlId"], "MSG1")

    def test_message_type_is_filled_from_msh_when_not_supplied_upstream(self) -> None:
        self._run(A31, MAPPING_NHS_ID_UPDATE)

        _, props = self._published()
        self.assertEqual(props["MessageType"], "ADT^A31^ADT_A05")

    def test_merge_publishes_merge_parameters_for_a40(self) -> None:
        self.assertTrue(self._run(A40_WITHOUT_NHS, MAPPING_MERGE, INCOMING_PROPS))

        payload, props = self._published()
        self.assertEqual(
            payload,
            {
                "OldIdentifier": "OLD-001",
                "OldIdentifierAssigningAuthority": "WLIMS",
                "NewIdentifier": "LIMS-77",
                "NewIdentifierAssigningAuthority": "WLIMS",
            },
        )
        self.assertNotIn("TrrrRequestType", props)

    def test_nhs_id_update_dead_letters_a40_without_nhs_identifier_without_publishing(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self._run(A40_WITHOUT_NHS, MAPPING_NHS_ID_UPDATE)

        self.assertEqual(ctx.exception.reason, "MappingFailed")
        self.assertEqual(ctx.exception.description, "Missing NHS identifier")
        self.sender.send_text_message.assert_not_called()
        self.event_logger.log_message_failed.assert_called_once()

    def test_merge_dead_letters_a40_without_mrg(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self._run(A40_WITHOUT_MRG, MAPPING_MERGE)

        self.assertEqual(ctx.exception.description, "Missing old identifier")
        self.sender.send_text_message.assert_not_called()

    def test_publish_failure_returns_false_for_retry(self) -> None:
        self.sender.send_text_message.side_effect = RuntimeError("bus unavailable")

        self.assertFalse(self._run(A31, MAPPING_NHS_ID_UPDATE))
        self.event_logger.log_message_processed.assert_not_called()

    def test_logging_failure_after_publish_still_completes_message(self) -> None:
        self.event_logger.log_message_processed.side_effect = RuntimeError("logging down")

        self.assertTrue(self._run(A31, MAPPING_NHS_ID_UPDATE))
        self.sender.send_text_message.assert_called_once()

    def test_event_logs_never_contain_the_nhs_number(self) -> None:
        self._run(A31, MAPPING_NHS_ID_UPDATE)

        for call in self.event_logger.method_calls:
            for arg in list(call.args) + list(call.kwargs.values()):
                self.assertNotIn("9876543210", str(arg))


class TestBuildEgressProperties(unittest.TestCase):
    def test_does_not_mutate_incoming_properties(self) -> None:
        incoming = {"CorrelationId": "c1"}

        props = application.build_egress_properties(incoming, "MSG1", "ADT^A40^ADT_A39")

        self.assertEqual(incoming, {"CorrelationId": "c1"})
        self.assertEqual(props["MessageControlId"], "MSG1")

    def test_handles_missing_incoming_properties(self) -> None:
        props = application.build_egress_properties(None, "MSG1", "ADT^A31^ADT_A05")

        self.assertEqual(props, {"MessageControlId": "MSG1", "MessageType": "ADT^A31^ADT_A05"})


if __name__ == "__main__":
    unittest.main()
