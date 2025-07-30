import itertools
import os
import time
import unittest

from hl7apy.parser import parse_message

from hl7_chemo_transformer.chemocare_transformer import transform_chemocare_message
from tests.chemo_messages import chemo_messages


class TestTransformerPerformance(unittest.TestCase):
    def test_transformer_performance(self):
        num_messages = int(os.environ.get("NUM_MESSAGES", 100))

        print(f"Starting performance test: processing {num_messages} messages...")

        message_list = list(chemo_messages.values())
        self.assertTrue(message_list, "No test messages found in chemo_messages.py.")

        messages_to_process = itertools.islice(
            itertools.cycle(message_list), num_messages
        )

        messages_processed = 0
        start_time = time.time()

        for message_str in messages_to_process:
            hl7_msg = parse_message(message_str)
            _ = transform_chemocare_message(hl7_msg)
            messages_processed += 1

        end_time = time.time()
        total_time = end_time - start_time
        messages_per_second = (
            messages_processed / total_time if total_time > 0 else float("inf")
        )

        print("Performance Test Results")
        print("=" * 50)
        print(f"Total messages processed: {messages_processed}")
        print(f"Total time taken: {total_time:.4f} seconds")
        print(f"Messages per second: {messages_per_second:.2f}")
        print(f"Time per message: {total_time / messages_processed:.6f} seconds")
        print("=" * 50)


if __name__ == "__main__":
    unittest.main()
