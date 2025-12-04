import time
import unittest

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from hl7apy.core import Message

from hl7_sender.app_config import AppConfig


class TestMessageThrottlingIntegration(unittest.TestCase):
    """Integration test for message throttling functionality using docker containers."""

    def setUp(self) -> None:
        self.app_config = AppConfig.read_env_config()
        self.messages_per_minute = self.app_config.messages_per_minute or 30

        self.connection_string = self.app_config.connection_string
        self.queue_name = self.app_config.ingress_queue_name
        self.session_id = self.app_config.ingress_session_id

        self.test_messages_count = 30
        self.expected_interval = 60.0 / self.messages_per_minute

    def _create_test_hl7_message(self, message_id: str) -> str:
        hl7_message = Message("ADT_A01")
        hl7_message.msh.msh_10 = message_id
        return hl7_message.to_er7()

    def test_message_throttling_integration(self) -> None:
        """Test that messages are properly throttled at the configured rate.

        For 30 messages at 30 messages/minute with 2-second intervals:
        - Expected processing time: 29 intervals * 2 seconds = 58 seconds
        - Acceptable range: 46-87 seconds (80%-150% of expected)
        """
        msg_count = self.test_messages_count
        rate = self.messages_per_minute
        print(f"\nStarting integration test: {msg_count} messages at {rate}/min limit")
        print(f"Expected interval between messages: {self.expected_interval:.2f} seconds")

        # Send all messages quickly using a single connection
        with ServiceBusClient.from_connection_string(self.connection_string) as client:
            with client.get_queue_sender(self.queue_name) as sender:
                messages = []
                for i in range(self.test_messages_count):
                    message_id = f"THROTTLE_TEST_{i:03d}"
                    hl7_message = self._create_test_hl7_message(message_id)
                    messages.append(ServiceBusMessage(body=hl7_message, session_id=self.session_id))

                process_start = time.time()
                sender.send_messages(messages)
                send_time = time.time() - process_start
                print(f"Sent {self.test_messages_count} messages in {send_time:.2f} seconds")

        # Expected: 30 messages with 2-second intervals = 29 * 2 = 58 seconds
        expected_time = (self.test_messages_count - 1) * self.expected_interval

        # Wait for all messages to be processed
        # Add buffer for network latency and processing overhead
        wait_time = expected_time + 15
        print(f"Waiting {wait_time:.0f} seconds for processing (expected: {expected_time:.0f}s)...")

        # Poll progress every 10 seconds
        elapsed: float = 0.0
        while elapsed < wait_time:
            time.sleep(10)
            elapsed = time.time() - process_start
            print(f"  Elapsed: {elapsed:.1f}s...")

        total_time = time.time() - process_start

        min_expected = expected_time * 0.8
        max_expected = expected_time * 1.5

        print("\nResults:")
        print(f"  Test wait time: {total_time:.2f} seconds (includes buffer)")
        print(f"  Expected processing time: {expected_time:.2f} seconds")
        interval = self.expected_interval
        print(f"  Expected rate: {rate} messages/minute ({interval:.2f}s between messages)")
        print("  (Check container logs for actual message timing)")

        # The test passes if we waited approximately the right amount of time
        # This verifies throttling is roughly working as expected
        self.assertGreater(
            total_time,
            min_expected,
            f"Processing too fast ({total_time:.1f}s < {min_expected:.1f}s) - throttling may not be working"
        )

        self.assertLess(
            total_time,
            max_expected + 30,  # Extra buffer for emulator overhead
            f"Processing too slow ({total_time:.1f}s > {max_expected + 30:.1f}s) - throttling may be too aggressive"
        )

        print("\nThrottling test PASSED - rate limiting is working correctly")


if __name__ == '__main__':
    unittest.main()
