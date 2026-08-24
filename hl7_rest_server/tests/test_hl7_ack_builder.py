"""Tests for HL7AckBuilder ACK/NACK string construction."""

from __future__ import annotations

import unittest

from hl7apy.parser import parse_message

from hl7_rest_server.hl7_ack_builder import HL7AckBuilder
from tests.helpers import VALID_ER7_MESSAGE


class HL7AckBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = HL7AckBuilder()
        self.msg = parse_message(VALID_ER7_MESSAGE, find_groups=False)

    def test_success_ack_format(self) -> None:
        ack = self.builder.build_success_ack(self.msg)
        self.assertTrue(ack.startswith("MSH|^~\\&|DHCW|cymru.nhs.uk|252|252|"))
        self.assertIn("|ACK|MSGID12345|P|2.5", ack)
        self.assertIn("\r\nMSA|AA|MSGID12345|Message received successfully.", ack)

    def test_validation_nack_echoes_control_id(self) -> None:
        nack = self.builder.build_validation_nack(self.msg, "Bad DOB")
        self.assertIn("MSA|AE|MSGID12345|Bad DOB", nack)

    def test_generic_nack_generates_control_id(self) -> None:
        nack = self.builder.build_generic_nack("Unparsable")
        self.assertIn("MSH|^~\\&|DHCW|cymru.nhs.uk|||", nack)
        control_id = nack.split("MSA|AE|")[1].split("|")[0]
        self.assertTrue(control_id)
        self.assertLessEqual(len(control_id), 20)
        self.assertIn("|2.5.1", nack)

    def test_generated_control_id_is_bounded(self) -> None:
        self.assertLessEqual(len(self.builder.generate_message_control_id()), 20)


if __name__ == "__main__":
    unittest.main()
