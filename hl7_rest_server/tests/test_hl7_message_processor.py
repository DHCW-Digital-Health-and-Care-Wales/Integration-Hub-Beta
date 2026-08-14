"""Unit tests for Hl7MessageProcessor pipeline behaviour."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from hl7_rest_server.errors import Hl7ParseError, Hl7ValidationError
from tests.helpers import VALID_ER7_MESSAGE, build_test_context


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


if __name__ == "__main__":
    unittest.main()
