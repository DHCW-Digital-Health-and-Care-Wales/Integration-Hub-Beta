import unittest

from hl7_sender.ack_processor import get_ack_result


def generate_ack_msg(ack_code: str) -> str:
    return ("MSH|^~\\&|SENDER|SENDER_APP|RECEIVER|RECEIVER_APP|20250101000000||ACK^A01|123456|P|2.5\r"
            f"MSA|{ack_code}|123456\r")

class TestGetAckResult(unittest.TestCase):

    def test_valid_ack_aa(self):
        result = get_ack_result(generate_ack_msg("AA"))

        self.assertTrue(result.success)

    def test_valid_ack_ca(self):
        result = get_ack_result(generate_ack_msg("CA"))

        self.assertTrue(result.success)

    def test_negative_ack_ae(self):
        result = get_ack_result(generate_ack_msg("AE"))

        self.assertFalse(result.success)
        self.assertIn('Negative ACK received: AE', result.error_reason)

    def test_negative_ack_ar(self):
        result = get_ack_result(generate_ack_msg("AR"))

        self.assertFalse(result.success)
        self.assertIn('Negative ACK received: AR', result.error_reason)

    def test_non_ack_message(self):
        non_ack_message = (
            "MSH|^~\\&|SENDER|SENDER_APP|RECEIVER|RECEIVER_APP|20250101000000||ADT^A01|111111|P|2.5\r"
            "PID|1||123456^^^Hospital^MR||Doe^John\r"
        )

        result = get_ack_result(non_ack_message)

        self.assertFalse(result.success)
        self.assertIn('Received a non-ACK message', result.error_reason)

    def test_malformed_message(self):
        result = get_ack_result("This is not a valid HL7 message")

        self.assertFalse(result.success)
        self.assertTrue('Exception occurred' in result.error_reason)

if __name__ == '__main__':
    unittest.main()
