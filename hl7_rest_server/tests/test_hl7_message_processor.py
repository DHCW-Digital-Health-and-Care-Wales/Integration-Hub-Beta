"""Unit tests for Hl7MessageProcessor pipeline behaviour."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from hl7_validation import ValidationResult

from hl7_rest_server.errors import Hl7ParseError, Hl7ValidationError
from tests.helpers import (
    RISP_A28_MESSAGE,
    RISP_A40_MESSAGE,
    RISP_ORU_R01_MESSAGE,
    VALID_ER7_MESSAGE,
    build_test_context,
)


class Hl7MessageProcessorTests(unittest.TestCase):
    def test_valid_message_sends_to_store_then_service_bus(self) -> None:
        context, sender, store = build_test_context()
        manager = MagicMock()
        manager.attach_mock(store.send_to_store, "store")
        manager.attach_mock(sender.send_text_message, "send")

        ack = context.processor.process(VALID_ER7_MESSAGE)

        self.assertIn("MSA|AA|MSGID12345", ack)
        # Store must be attempted before the Service Bus send.
        self.assertEqual([c[0] for c in manager.mock_calls], ["store", "send"])

    def test_service_bus_send_is_called_once(self) -> None:
        context, sender, _ = build_test_context()
        context.processor.process(VALID_ER7_MESSAGE)
        sender.send_text_message.assert_called_once()

    def test_unparsable_message_raises_parse_error(self) -> None:
        context, sender, _ = build_test_context()
        with self.assertRaises(Hl7ParseError):
            context.processor.process("not a valid hl7 message")
        sender.send_text_message.assert_not_called()

    def test_version_mismatch_raises_validation_error(self) -> None:
        context, sender, _ = build_test_context(hl7_version="2.9")
        with self.assertRaises(Hl7ValidationError) as ctx:
            context.processor.process(VALID_ER7_MESSAGE)
        self.assertIn("MSA|AE|MSGID12345", ctx.exception.nack_message)
        sender.send_text_message.assert_not_called()

    def test_store_failure_is_non_blocking(self) -> None:
        context, sender, store = build_test_context()
        store.send_to_store.side_effect = RuntimeError("store down")
        # Store failure must not prevent forwarding or a successful ACK.
        ack = context.processor.process(VALID_ER7_MESSAGE)
        self.assertIn("MSA|AA|", ack)
        sender.send_text_message.assert_called_once()

    def test_service_bus_failure_propagates(self) -> None:
        context, sender, _ = build_test_context()
        sender.send_text_message.side_effect = RuntimeError("bus down")
        with self.assertRaises(RuntimeError):
            context.processor.process(VALID_ER7_MESSAGE)


class Hl7MessageProcessorRispFlowTests(unittest.TestCase):
    """Tests for the RISP flow's multi-destination fan-out (plan §3a)."""

    def test_a28_sends_only_to_mpi_transformer(self) -> None:
        context, sender, _ = build_test_context(flow_name="risp")
        assert context.wrrs_sender_client is not None
        ack = context.processor.process(RISP_A28_MESSAGE)

        self.assertIn("MSA|AA|RISPMSG001", ack)
        sender.send_text_message.assert_called_once()
        context.wrrs_sender_client.send_text_message.assert_not_called()

    def test_a40_sends_to_both_mpi_transformer_and_wrrs(self) -> None:
        context, sender, _ = build_test_context(flow_name="risp")
        assert context.wrrs_sender_client is not None
        ack = context.processor.process(RISP_A40_MESSAGE)

        self.assertIn("MSA|AA|RISPMSG002", ack)
        sender.send_text_message.assert_called_once()
        context.wrrs_sender_client.send_text_message.assert_called_once()

        # The MPI transformer destination gets the raw ER7 payload.
        mpi_args = sender.send_text_message.call_args
        self.assertEqual(mpi_args[0][0], RISP_A40_MESSAGE)

        # The WRRS destination gets an XML payload with the WRRS workflow id.
        wrrs_args = context.wrrs_sender_client.send_text_message.call_args
        self.assertIn("<", wrrs_args[0][0])
        self.assertEqual(wrrs_args[0][1]["WorkflowID"], "risp-to-wrrs")

    def test_oru_r01_sends_only_to_wrrs_after_schema_validation(self) -> None:
        context, sender, _ = build_test_context(flow_name="risp")
        assert context.wrrs_sender_client is not None
        fake_xml = "<ORU_R01>...</ORU_R01>"
        with patch(
            "hl7_rest_server.risp_routing.validate_and_convert_parsed_message_with_flow_schema",
            return_value=ValidationResult(
                xml_string=fake_xml,
                structure_id="ORU_R01",
                message_type="ORU",
                trigger_event="R01",
                message_control_id="RISPMSG003",
                is_valid=True,
                error_message=None,
            ),
        ):
            ack = context.processor.process(RISP_ORU_R01_MESSAGE)

        self.assertIn("MSA|AA|RISPMSG003", ack)
        sender.send_text_message.assert_not_called()
        context.wrrs_sender_client.send_text_message.assert_called_once()
        wrrs_args = context.wrrs_sender_client.send_text_message.call_args
        self.assertEqual(wrrs_args[0][0], fake_xml)

    def test_wrong_sending_facility_rejects_with_no_sends(self) -> None:
        context, sender, _ = build_test_context(flow_name="risp")
        assert context.wrrs_sender_client is not None
        bad_message = RISP_A28_MESSAGE.replace("|349|349|", "|999|999|")
        with self.assertRaises(Hl7ValidationError):
            context.processor.process(bad_message)
        sender.send_text_message.assert_not_called()
        context.wrrs_sender_client.send_text_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
