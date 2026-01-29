"""
=============================================================================
WEEK 3 - EXERCISE 2 SOLUTION: ACK Processor Unit Tests
=============================================================================

This module contains unit tests for the get_ack_result() function in the
ack_processor module. These tests verify that ACK messages are correctly
validated and that edge cases are handled properly.

WHY MOCK THE LOGGER?
--------------------
We use @patch to mock the logger because:
1. It prevents log output from cluttering test output
2. We can verify that the correct log messages are being generated
3. It isolates the test from logging configuration

RUNNING THESE TESTS:
--------------------
From the training_hl7_sender directory:
    uv run python -m unittest tests.test_ack_processor -v

Or run all tests:
    uv run python -m unittest discover tests -v
"""

import unittest
from unittest.mock import MagicMock, patch

# Import the function we're testing
from training_hl7_sender.ack_processor import get_ack_result


def generate_ack_msg(ack_code: str) -> str:
    """
    Generate a valid HL7 ACK message with the specified acknowledgment code.

    This helper function creates a properly formatted ACK message that can be
    used in tests. It's easier than manually constructing messages each time.

    Args:
        ack_code: The ACK code to include in MSA-1 (e.g., "AA", "AE", "AR", "CA")

    Returns:
        A valid HL7 ACK message string

    Example:
        >>> generate_ack_msg("AA")
        'MSH|^~\\&|SENDER|...|ACK^A01|...\rMSA|AA|123456\r'
    """
    return (
        "MSH|^~\\&|SENDER|SENDER_APP|RECEIVER|RECEIVER_APP|20260125120000||ACK^A01|123456|P|2.5\r"
        f"MSA|{ack_code}|123456\r"
    )


class TestGetAckResult(unittest.TestCase):
    """
    WEEK 3 - EXERCISE 2 SOLUTION: Test cases for get_ack_result()

    This test class verifies that the ACK processor correctly handles:
    - Success codes (AA, CA)
    - Error codes (AE, AR)
    - Invalid messages

    Each test method follows the Arrange-Act-Assert pattern:
    1. Arrange: Set up test data (the ACK message)
    2. Act: Call get_ack_result()
    3. Assert: Verify the result and any side effects (logging)
    """

    # =========================================================================
    # SUCCESS CASES - These ACK codes indicate the message was accepted
    # =========================================================================

    @patch("training_hl7_sender.ack_processor.logger")
    def test_valid_ack_aa_returns_true(self, mock_logger: MagicMock) -> None:
        """
        Test that ACK code 'AA' (Application Accept) returns True.

        AA is the most common success code. It means the receiving application
        accepted the message and processed it successfully.
        """
        # Arrange: Create an ACK message with AA code
        ack_message = generate_ack_msg("AA")

        # Act: Call the function under test
        result = get_ack_result(ack_message)

        # Assert: Should return True for success
        self.assertTrue(result)
        # Verify the success log message was generated
        mock_logger.info.assert_called_once_with("Valid ACK received.")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_valid_ack_ca_returns_true(self, mock_logger: MagicMock) -> None:
        """
        Test that ACK code 'CA' (Commit Accept) returns True.

        CA would usually mean the message was committed to storage
        by the receiving application.
        """
        # Arrange
        ack_message = generate_ack_msg("CA")

        # Act
        result = get_ack_result(ack_message)

        # Assert
        self.assertTrue(result)
        mock_logger.info.assert_called_once_with("Valid ACK received.")

    # =========================================================================
    # FAILURE CASES - These ACK codes indicate the message was rejected
    # =========================================================================

    @patch("training_hl7_sender.ack_processor.logger")
    def test_negative_ack_ae_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that ACK code 'AE' (Application Error) returns False.

        AE means the receiving application encountered an error processing
        the message. The message should be retried or investigated.
        """
        # Arrange
        ack_message = generate_ack_msg("AE")

        # Act
        result = get_ack_result(ack_message)

        # Assert
        self.assertFalse(result)
        # Verify the error log includes the ACK code and control ID
        mock_logger.error.assert_called_once_with("Negative ACK received: AE for: 123456")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_negative_ack_ar_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that ACK code 'AR' (Application Reject) returns False.

        AR means the receiving application rejected the message. This is
        typically due to a problem with the message content itself.
        """
        # Arrange
        ack_message = generate_ack_msg("AR")

        # Act
        result = get_ack_result(ack_message)

        # Assert
        self.assertFalse(result)
        mock_logger.error.assert_called_once_with("Negative ACK received: AR for: 123456")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_negative_ack_ce_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that ACK code 'CE' (Commit Error) returns False.

        CE is used in enhanced acknowledgment mode. It means there was an
        error committing the message to storage.
        """
        # Arrange
        ack_message = generate_ack_msg("CE")

        # Act
        result = get_ack_result(ack_message)

        # Assert
        self.assertFalse(result)
        mock_logger.error.assert_called_once_with("Negative ACK received: CE for: 123456")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_negative_ack_cr_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that ACK code 'CR' (Commit Reject) returns False.

        CR is used in enhanced acknowledgment mode. It means the commit
        was rejected.
        """
        # Arrange
        ack_message = generate_ack_msg("CR")

        # Act
        result = get_ack_result(ack_message)

        # Assert
        self.assertFalse(result)
        mock_logger.error.assert_called_once_with("Negative ACK received: CR for: 123456")

    # =========================================================================
    # EDGE CASES - Invalid or unexpected message formats
    # =========================================================================

    @patch("training_hl7_sender.ack_processor.logger")
    def test_non_ack_message_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that a valid HL7 message WITHOUT an MSA segment returns False.

        Not all HL7 messages are ACKs. An ADT (Admit/Discharge/Transfer) message,
        for example, doesn't have an MSA segment. If we receive one of these
        instead of an ACK, we should return False.
        """
        # Arrange: Create a valid HL7 message but NOT an ACK (no MSA segment)
        non_ack_message = (
            "MSH|^~\\&|SENDER|SENDER_APP|RECEIVER|RECEIVER_APP|20260125120000||ADT^A01|111111|P|2.5\r"
            "PID|1||123456^^^Hospital^MR||Doe^John\r"
        )

        # Act
        result = get_ack_result(non_ack_message)

        # Assert
        self.assertFalse(result)
        mock_logger.error.assert_called_once_with("Received a non-ACK message")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_malformed_message_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that a completely malformed message returns False.

        If the message isn't valid HL7 at all, the parser will throw an
        exception. Our function should catch this and return False, never
        raising an exception to the caller.
        """
        # Arrange: Create garbage that isn't HL7
        malformed_message = "This is not a valid HL7 message at all!"

        # Act
        result = get_ack_result(malformed_message)

        # Assert
        self.assertFalse(result)
        # The exception handler should log the error
        mock_logger.exception.assert_called_once_with("Exception while parsing ACK message")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_empty_message_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that an empty string returns False.

        Edge case: what if we receive an empty response? The function should
        handle this gracefully without crashing.
        """
        # Arrange
        empty_message = ""

        # Act
        result = get_ack_result(empty_message)

        # Assert
        self.assertFalse(result)
        mock_logger.exception.assert_called_once_with("Exception while parsing ACK message")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_whitespace_only_message_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that a whitespace-only string returns False.

        Another edge case: what if we receive just whitespace? This could
        happen if there are network issues or encoding problems.
        """
        # Arrange
        whitespace_message = "   \n\r\t   "

        # Act
        result = get_ack_result(whitespace_message)

        # Assert
        self.assertFalse(result)
        mock_logger.exception.assert_called_once_with("Exception while parsing ACK message")

    @patch("training_hl7_sender.ack_processor.logger")
    def test_unknown_ack_code_returns_false(self, mock_logger: MagicMock) -> None:
        """
        Test that an unrecognized ACK code returns False.

        If we receive an ACK code that isn't in our SUCCESS_ACK_CODES list,
        we should treat it as a failure. This is defensive programming -
        we only accept codes we explicitly recognize as successful.
        """
        # Arrange: Use a made-up ACK code
        ack_message = generate_ack_msg("XX")  # Not a real ACK code

        # Act
        result = get_ack_result(ack_message)

        # Assert
        self.assertFalse(result)
        mock_logger.error.assert_called_once_with("Negative ACK received: XX for: 123456")


# =============================================================================
# WEEK 3 - EXERCISE 2 SOLUTION: Test Runner
# =============================================================================
# This block allows running the tests directly with:
#     uv run python -m tests.test_ack_processor
# =============================================================================
if __name__ == "__main__":
    unittest.main()
