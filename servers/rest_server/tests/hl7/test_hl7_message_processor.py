"""Unit tests for Hl7MessageProcessor pipeline behaviour."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from field_utils_lib import get_hl7_field_value
from hl7_message_processor import ProcessedMessage

from rest_server.hl7.errors import Hl7ParseError, Hl7ValidationError
from tests.hl7.helpers import (
    RISP_A28_MESSAGE,
    RISP_A40_MESSAGE,
    RISP_ORU_R01_MESSAGE,
    VALID_ER7_MESSAGE,
    build_test_context,
)


class Hl7MessageProcessorTests(unittest.TestCase):
    def test_valid_message_sends_to_store_then_service_bus(self) -> None:
        context, sender, store, _ = build_test_context()
        manager = MagicMock()
        manager.attach_mock(store.send_to_store, "store")
        manager.attach_mock(sender.send_text_message, "send")

        ack = context.processor.process(VALID_ER7_MESSAGE)

        self.assertIn("MSA|AA|MSGID12345", ack)
        # Store must be attempted before the Service Bus send.
        self.assertEqual([c[0] for c in manager.mock_calls], ["store", "send"])

    def test_service_bus_send_is_called_once(self) -> None:
        context, sender, _, _ = build_test_context()
        context.processor.process(VALID_ER7_MESSAGE)
        sender.send_text_message.assert_called_once()

    def test_unparsable_message_raises_parse_error(self) -> None:
        context, sender, _, _ = build_test_context()
        with self.assertRaises(Hl7ParseError):
            context.processor.process("not a valid hl7 message")
        sender.send_text_message.assert_not_called()

    def test_version_mismatch_raises_validation_error(self) -> None:
        context, sender, _, _ = build_test_context(hl7_version="2.9")
        with self.assertRaises(Hl7ValidationError) as ctx:
            context.processor.process(VALID_ER7_MESSAGE)
        self.assertIn("MSA|AR|MSGID12345", ctx.exception.nack_message)
        sender.send_text_message.assert_not_called()

    def test_store_failure_is_non_blocking(self) -> None:
        context, sender, store, _ = build_test_context()
        store.send_to_store.side_effect = RuntimeError("store down")
        # Store failure must not prevent forwarding or a successful ACK.
        ack = context.processor.process(VALID_ER7_MESSAGE)
        self.assertIn("MSA|AA|", ack)
        sender.send_text_message.assert_called_once()

    def test_service_bus_failure_propagates(self) -> None:
        context, sender, _, _ = build_test_context()
        sender.send_text_message.side_effect = RuntimeError("bus down")
        with self.assertRaises(RuntimeError):
            context.processor.process(VALID_ER7_MESSAGE)

    def test_sourcesystem_extracted_from_composite_msh3_in_store_and_forward(self) -> None:
        """Composite MSH-3 (e.g. APP^OID^ISO) extracts the first component instead of the raw composite."""
        context, sender, store, _ = build_test_context()
        composite_msg = VALID_ER7_MESSAGE.replace("|252|252|", "|COMP_APP^1.2.3.4^ISO|FAC|")

        context.processor.process(composite_msg)

        store.send_to_store.assert_called_once()
        self.assertEqual(store.send_to_store.call_args.kwargs["source_system"], "COMP_APP")

        sender.send_text_message.assert_called_once()
        forwarded_props = sender.send_text_message.call_args.args[1]
        self.assertEqual(forwarded_props["SourceSystem"], "COMP_APP")

    def test_sourcesystem_extracted_from_simple_msh3_in_store_and_forward(self) -> None:
        """Simple scalar MSH-3 extracts correctly in both stored and forwarded metadata."""
        context, sender, store, _ = build_test_context()
        simple_msg = VALID_ER7_MESSAGE.replace("|252|252|", "|SIMPLE_APP|FAC|")

        context.processor.process(simple_msg)

        store.send_to_store.assert_called_once()
        self.assertEqual(store.send_to_store.call_args.kwargs["source_system"], "SIMPLE_APP")

        sender.send_text_message.assert_called_once()
        forwarded_props = sender.send_text_message.call_args.args[1]
        self.assertEqual(forwarded_props["SourceSystem"], "SIMPLE_APP")

    def test_sourcesystem_empty_when_msh3_is_empty_in_store_and_forward(self) -> None:
        """Empty MSH-3 yields an empty SourceSystem string in both stored and forwarded metadata."""
        context, sender, store, _ = build_test_context()
        empty_msh3_msg = VALID_ER7_MESSAGE.replace("|252|252|", "||FAC|")

        context.processor.process(empty_msh3_msg)

        store.send_to_store.assert_called_once()
        self.assertEqual(store.send_to_store.call_args.kwargs["source_system"], "")

        sender.send_text_message.assert_called_once()
        forwarded_props = sender.send_text_message.call_args.args[1]
        self.assertEqual(forwarded_props["SourceSystem"], "")

    def test_sourcesystem_fallback_precedence_in_store_and_forward(self) -> None:
        """Test fallback precedence: msh_3.msh_3_1 -> msh_3.hd_1 -> msh_3."""
        context, sender, store, _ = build_test_context()

        # When msh_3_1 is absent but hd_1 is present:
        def hd1_side_effect(segment: object, path: str) -> str:
            if path == "msh_3.msh_3_1":
                return ""
            if path == "msh_3.hd_1":
                return "HD1_FALLBACK"
            if path == "msh_3":
                return "RAW_MSH3"
            return get_hl7_field_value(segment, path)

        with patch("rest_server.hl7.hl7_message_processor.get_hl7_field_value", side_effect=hd1_side_effect):
            context.processor.process(VALID_ER7_MESSAGE)

        self.assertEqual(store.send_to_store.call_args.kwargs["source_system"], "HD1_FALLBACK")
        self.assertEqual(sender.send_text_message.call_args.args[1]["SourceSystem"], "HD1_FALLBACK")

        # When both msh_3_1 and hd_1 are absent but raw msh_3 is present:
        def raw_side_effect(segment: object, path: str) -> str:
            if path in ("msh_3.msh_3_1", "msh_3.hd_1"):
                return ""
            if path == "msh_3":
                return "RAW_FALLBACK"
            return get_hl7_field_value(segment, path)

        sender.reset_mock()
        store.reset_mock()
        with patch("rest_server.hl7.hl7_message_processor.get_hl7_field_value", side_effect=raw_side_effect):
            context.processor.process(VALID_ER7_MESSAGE)

        self.assertEqual(store.send_to_store.call_args.kwargs["source_system"], "RAW_FALLBACK")
        self.assertEqual(sender.send_text_message.call_args.args[1]["SourceSystem"], "RAW_FALLBACK")


class Hl7MessageProcessorRispFlowTests(unittest.TestCase):
    """Tests for the RISP flow's multi-destination fan-out."""

    def test_a28_sends_only_to_mpi_transformer(self) -> None:
        context, sender, _, wrrs = build_test_context(flow_name="risp")
        assert wrrs is not None
        ack = context.processor.process(RISP_A28_MESSAGE)

        self.assertIn("MSA|AA|RISPMSG001", ack)
        sender.send_text_message.assert_called_once()
        wrrs.send_text_message.assert_not_called()

        # RISP messages carry a MessageType application property (MSH.9.2 trigger event) so
        # Service Bus subscriptions can filter on it - see custom_message_properties.build_risp_properties.
        mpi_args = sender.send_text_message.call_args
        self.assertEqual(mpi_args[0][1]["MessageType"], "A28")
        self.assertEqual(mpi_args[0][1]["MessageStructure"], "ADT_A05")

    def test_a28_without_message_structure_publishes_resolved_structure(self) -> None:
        context, sender, _, wrrs = build_test_context(flow_name="risp")
        assert wrrs is not None
        message_without_structure = RISP_A28_MESSAGE.replace("^ADT_A05", "")

        context.processor.process(message_without_structure)

        sender.send_text_message.assert_called_once()
        self.assertEqual(sender.send_text_message.call_args[0][1]["MessageStructure"], "ADT_A28")

    def test_a40_sends_to_both_mpi_transformer_and_wrrs(self) -> None:
        context, sender, _, wrrs = build_test_context(flow_name="risp")
        assert wrrs is not None
        ack = context.processor.process(RISP_A40_MESSAGE)

        self.assertIn("MSA|AA|RISPMSG002", ack)
        sender.send_text_message.assert_called_once()
        wrrs.send_text_message.assert_called_once()

        # The MPI transformer destination gets the raw ER7 payload.
        mpi_args = sender.send_text_message.call_args
        self.assertEqual(mpi_args[0][0], RISP_A40_MESSAGE)
        self.assertEqual(mpi_args[0][1]["MessageType"], "A40")
        self.assertEqual(mpi_args[0][1]["MessageStructure"], "ADT_A39")

        # The WRRS destination gets an XML payload with the WRRS workflow id, and the same
        # MessageType property (both destination copies share the tracking properties dict).
        wrrs_args = wrrs.send_text_message.call_args
        self.assertIn("<", wrrs_args[0][0])
        self.assertEqual(wrrs_args[0][1]["WorkflowID"], "risp-to-wrrs")
        self.assertEqual(wrrs_args[0][1]["MessageType"], "A40")
        self.assertEqual(wrrs_args[0][1]["MessageStructure"], "ADT_A39")

    def test_oru_r01_sends_only_to_wrrs_after_schema_validation(self) -> None:
        context, sender, _, wrrs = build_test_context(flow_name="risp")
        assert wrrs is not None
        fake_xml = "<ORU_R01>...</ORU_R01>"
        fake_result = ProcessedMessage(
            xml=fake_xml, structure_id="ORU_R01", version="2.5.1", xsd_path=Path("/schemas/ORU_R01.xsd")
        )
        with (
            patch("rest_server.hl7.risp_routing.process_er7", return_value=fake_result),
            patch("rest_server.hl7.risp_routing.validate_xml"),
        ):
            ack = context.processor.process(RISP_ORU_R01_MESSAGE)

        self.assertIn("MSA|AA|RISPMSG003", ack)
        sender.send_text_message.assert_not_called()
        wrrs.send_text_message.assert_called_once()
        wrrs_args = wrrs.send_text_message.call_args
        self.assertEqual(wrrs_args[0][0], fake_xml)
        self.assertEqual(wrrs_args[0][1]["MessageStructure"], "ORU_R01")

    def test_oru_r01_composite_msh3_sourcesystem_in_wrrs_metadata(self) -> None:
        context, sender, store, wrrs = build_test_context(flow_name="risp")
        assert wrrs is not None
        composite_oru = RISP_ORU_R01_MESSAGE.replace("|350|350|", "|350^2.16.840.1.113883.2.1.8.1.5.350^ISO|350|")
        fake_xml = "<ORU_R01>...</ORU_R01>"
        fake_result = ProcessedMessage(
            xml=fake_xml, structure_id="ORU_R01", version="2.5.1", xsd_path=Path("/schemas/ORU_R01.xsd")
        )
        with (
            patch("rest_server.hl7.risp_routing.process_er7", return_value=fake_result),
            patch("rest_server.hl7.risp_routing.validate_xml"),
        ):
            context.processor.process(composite_oru)

        wrrs.send_text_message.assert_called_once()
        self.assertEqual(wrrs.send_text_message.call_args[0][1]["SourceSystem"], "350")
        store.send_to_store.assert_called_once()
        self.assertEqual(store.send_to_store.call_args.kwargs["source_system"], "350")

    def test_wrong_sending_facility_rejects_with_no_sends(self) -> None:
        context, sender, _, wrrs = build_test_context(flow_name="risp")
        assert wrrs is not None
        bad_message = RISP_A28_MESSAGE.replace("|349|349|", "|999|999|")
        with self.assertRaises(Hl7ValidationError):
            context.processor.process(bad_message)
        sender.send_text_message.assert_not_called()
        wrrs.send_text_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
