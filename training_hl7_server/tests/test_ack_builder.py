"""
===========================================================================
Unit tests for the ACK Builder (Training HL7 Server)
===========================================================================

These tests verify that AckBuilder creates valid HL7 ACK messages.

Key ideas for beginners:
- An ACK confirms whether the receiver accepted the message.
- The ACK should copy key fields and swap sender/receiver details.
"""

import unittest

from hl7apy.parser import parse_message  # type: ignore[import-untyped]

from training_hl7_server.ack_builder import AckBuilder
from training_hl7_server.constants import Hl7Constants


class TestAckBuilder(unittest.TestCase):
    """Test cases for AckBuilder class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.ack_builder = AckBuilder()

        # Sample ADT^A28 message for testing
        self.sample_hl7 = (
            "MSH|^~\\&|169|169|100|100|20240115102000||ADT^A28|MSG001|P|2.3.1|||AL|NE|\r"
            "EVN|A28|20240115102000||01|\r"
            "PID|1||1234567890^^^NHS^NH||Jones^Sarah^A||19900101|F|||"
            "123 High Street^^Cardiff^^CF10 1AA^GBR^H||029 2000 1234||||||||||||||||||||\r"
        )
        self.original_msg = parse_message(self.sample_hl7)

    def test_build_ack_creates_valid_ack_message(self) -> None:
        """Test that build_ack creates a valid ACK message."""
        # Act: Build the ACK using the message control ID and original message
        ack = self.ack_builder.build_ack("MSG001", self.original_msg)

        # Assert: Message type is ACK
        self.assertEqual(str(ack.msh.msh_9.msh_9_1.value), "ACK")

        # Assert: Standard HL7 separators are preserved
        self.assertEqual(str(ack.msh.msh_1.value), Hl7Constants.FIELD_SEPARATOR)
        self.assertEqual(str(ack.msh.msh_2.value), Hl7Constants.ENCODING_CHARACTERS)

        # Assert: Message control ID is echoed back
        self.assertEqual(str(ack.msh.msh_10.value), "MSG001")

        # Assert: Default ACK code is AA (Accept)
        self.assertEqual(str(ack.msa.msa_1.value), Hl7Constants.ACK_CODE_ACCEPT)
        self.assertEqual(str(ack.msa.msa_2.value), "MSG001")

    def test_build_ack_with_error_code(self) -> None:
        """Test that build_ack can create an error ACK (AE)."""
        # Act: Build an error ACK with a message
        ack = self.ack_builder.build_ack(
            "MSG002",
            self.original_msg,
            ack_code=Hl7Constants.ACK_CODE_ERROR,
            error_message="Invalid message version",
        )

        # Assert: ACK code is AE (Error)
        self.assertEqual(str(ack.msa.msa_1.value), Hl7Constants.ACK_CODE_ERROR)

        # Assert: Error message is included for debugging
        self.assertEqual(str(ack.msa.msa_3.value), "Invalid message version")

    def test_build_ack_swaps_sender_and_receiver(self) -> None:
        """Test that build_ack correctly swaps sending and receiving applications."""
        # Act: Build an ACK and inspect MSH-3 to MSH-6 fields
        ack = self.ack_builder.build_ack("MSG001", self.original_msg)

        # Original: Sending App = 169, Sending Facility = 169
        #           Receiving App = 100, Receiving Facility = 100
        # ACK should reverse these
        self.assertEqual(str(ack.msh.msh_3.value), "100")  # Original receiving app
        self.assertEqual(str(ack.msh.msh_4.value), "100")  # Original receiving facility
        self.assertEqual(str(ack.msh.msh_5.value), "169")  # Original sending app
        self.assertEqual(str(ack.msh.msh_6.value), "169")  # Original sending facility

    def test_build_ack_includes_timestamp(self) -> None:
        """Test that build_ack includes a timestamp in MSH-7."""
        # Act
        ack = self.ack_builder.build_ack("MSG001", self.original_msg)

        # Assert: Timestamp field is not empty
        timestamp = str(ack.msh.msh_7)
        self.assertIsNotNone(timestamp)
        self.assertTrue(len(timestamp) > 0)

    def test_build_ack_includes_processing_id(self) -> None:
        """Test that build_ack includes processing ID from original message."""
        # Act
        ack = self.ack_builder.build_ack("MSG001", self.original_msg)

        # Assert: Processing ID matches original (P for Production)
        self.assertEqual(str(ack.msh.msh_11.value), "P")


if __name__ == "__main__":
    unittest.main()
