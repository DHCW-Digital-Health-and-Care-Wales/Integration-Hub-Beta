from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from message_bus_lib.dead_letter import DeadLetterMessage

from hl7_lims_wrrs_transformer.app_config import MappingTypeConfig
from hl7_lims_wrrs_transformer.message_processor import (
    INVALID_MESSAGE_REASON,
    UNSUPPORTED_MESSAGE_REASON,
    LimsWrrsMessageProcessor,
)
from tests.messages import A04_NHS_AND_LIMS, A31_NHS_AND_LIMS, A40_NHS_AND_LIMS

_TYPES = MappingTypeConfig(nhs_id_update="LIMS_NHS_ID_UPDATE", a40="ADT_A40")


def _inbound(er7: str, message_id: str | None = "orig-1") -> MagicMock:
    message = MagicMock()
    message.body = [er7.encode("utf-8")]
    message.message_id = message_id
    message.application_properties = {
        b"CorrelationId": b"corr-1",
        b"WorkflowID": b"lims-to-mpi",
        b"SourceSystem": b"328",
        b"MessageType": b"A40",
        b"traceparent": b"00-abc-def-01",
    }
    return message


class TestLimsWrrsMessageProcessor(unittest.TestCase):
    def setUp(self) -> None:
        self.sender = MagicMock()
        self.event_logger = MagicMock()
        self.processor = LimsWrrsMessageProcessor(self.sender, self.event_logger, _TYPES)

    def _sent(self) -> list[tuple[bytes, dict[str, str], str]]:
        return [
            (c.args[0], c.kwargs["custom_properties"], c.kwargs["message_id"])
            for c in self.sender.send_message.call_args_list
        ]

    def test_a31_publishes_single_nhs_id_update(self) -> None:
        self.assertTrue(self.processor.process(_inbound(A31_NHS_AND_LIMS)))

        sent = self._sent()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1]["MappingType"], "LIMS_NHS_ID_UPDATE")

    def test_a40_matching_both_rules_fans_out_two_independent_messages(self) -> None:
        self.assertTrue(self.processor.process(_inbound(A40_NHS_AND_LIMS)))

        sent = self._sent()
        self.assertEqual([props["MappingType"] for _, props, _ in sent], ["LIMS_NHS_ID_UPDATE", "ADT_A40"])
        self.assertEqual(len({props["ProcessingId"] for _, props, _ in sent}), 2)
        # The original MessageId and correlation ID are kept on every copy ...
        for _, props, _ in sent:
            self.assertEqual(props["OriginalMessageId"], "orig-1")
            self.assertEqual(props["CorrelationId"], "corr-1")
        # ... while the Service Bus message_id is per-path so duplicate detection keeps both copies.
        self.assertEqual([mid for _, _, mid in sent], ["orig-1-LIMS_NHS_ID_UPDATE", "orig-1-ADT_A40"])
        # Body is published unchanged (classification only, no mapping).
        self.assertEqual({body for body, _, _ in sent}, {A40_NHS_AND_LIMS.encode("utf-8")})

    def test_inbound_application_properties_are_preserved(self) -> None:
        self.processor.process(_inbound(A31_NHS_AND_LIMS))

        props = self._sent()[0][1]
        self.assertEqual(props["WorkflowID"], "lims-to-mpi")
        self.assertEqual(props["SourceSystem"], "328")
        self.assertEqual(props["MessageType"], "A40")
        self.assertEqual(props["traceparent"], "00-abc-def-01")

    def test_falls_back_to_msh_10_when_service_bus_message_id_missing(self) -> None:
        self.processor.process(_inbound(A31_NHS_AND_LIMS, message_id=None))

        self.assertEqual(self._sent()[0][1]["OriginalMessageId"], "MSG0001")

    def test_unsupported_message_is_dead_lettered_and_not_published(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.processor.process(_inbound(A04_NHS_AND_LIMS))

        self.assertEqual(ctx.exception.reason, UNSUPPORTED_MESSAGE_REASON)
        self.assertEqual(UNSUPPORTED_MESSAGE_REASON, "Unsupported message type")
        self.assertIn("orig-1", ctx.exception.description)
        self.assertIn("corr-1", ctx.exception.description)
        self.sender.send_message.assert_not_called()
        self.event_logger.log_message_failed.assert_called_once()
        self.assertEqual(self.event_logger.log_message_failed.call_args.kwargs["correlation_id"], "corr-1")

    def test_unparseable_message_is_dead_lettered(self) -> None:
        with self.assertRaises(DeadLetterMessage) as ctx:
            self.processor.process(_inbound("not an hl7 message"))

        self.assertEqual(ctx.exception.reason, INVALID_MESSAGE_REASON)
        self.sender.send_message.assert_not_called()

    def test_one_path_failing_does_not_stop_the_other_and_message_is_retried(self) -> None:
        self.sender.send_message.side_effect = [RuntimeError("boom"), None]

        result = self.processor.process(_inbound(A40_NHS_AND_LIMS))

        self.assertFalse(result)  # False => inbound message abandoned for redelivery
        self.assertEqual(self.sender.send_message.call_count, 2)
        self.event_logger.log_message_failed.assert_called_once()
        self.event_logger.log_message_processed.assert_called_once()

    def test_retry_reuses_deterministic_message_ids_for_duplicate_detection(self) -> None:
        self.sender.send_message.side_effect = [RuntimeError("boom"), None, None, None]

        self.processor.process(_inbound(A40_NHS_AND_LIMS))
        first_attempt_ids = [mid for _, _, mid in self._sent()]
        self.sender.send_message.reset_mock(side_effect=True)
        self.processor.process(_inbound(A40_NHS_AND_LIMS))

        self.assertEqual([mid for _, _, mid in self._sent()], first_attempt_ids)

    def test_events_logged_with_correlation_id(self) -> None:
        self.processor.process(_inbound(A31_NHS_AND_LIMS))

        self.assertEqual(self.event_logger.log_message_received.call_args.kwargs["correlation_id"], "corr-1")
        self.assertEqual(self.event_logger.log_message_processed.call_args.kwargs["correlation_id"], "corr-1")


if __name__ == "__main__":
    unittest.main()
