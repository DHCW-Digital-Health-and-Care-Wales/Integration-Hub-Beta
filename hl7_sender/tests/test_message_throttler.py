import unittest
from unittest.mock import patch

from hl7_sender.message_throttler import MessageThrottler


class TestMessageThrottler(unittest.TestCase):

    def test_no_throttling_when_messages_per_minute_is_none(self) -> None:
        throttler = MessageThrottler(messages_per_minute=None)

        with patch("time.sleep") as mock_sleep:
            for _ in range(100):
                throttler.wait_if_needed()
                throttler.record_message_sent()

            mock_sleep.assert_not_called()

    def test_no_throttling_when_under_limit(self) -> None:
        throttler = MessageThrottler(messages_per_minute=30)

        with patch("time.sleep") as mock_sleep:
            for _ in range(29):
                throttler.wait_if_needed()
                throttler.record_message_sent()

            mock_sleep.assert_not_called()

    @patch("hl7_sender.message_throttler.time")
    def test_throttling_when_at_limit(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(messages_per_minute=3)
        base_time = 1000.0
        mock_time.time.return_value = base_time

        for _ in range(3):
            throttler.wait_if_needed()
            throttler.record_message_sent()

        mock_time.sleep.assert_not_called()

        mock_time.time.return_value = base_time + 10
        throttler.wait_if_needed()

        mock_time.sleep.assert_called_once()
        sleep_duration = mock_time.sleep.call_args[0][0]
        self.assertAlmostEqual(sleep_duration, 50.0, places=1)

    @patch("hl7_sender.message_throttler.time")
    def test_sliding_window_allows_messages_after_expiry(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(messages_per_minute=2)
        base_time = 1000.0

        mock_time.time.return_value = base_time
        throttler.wait_if_needed()
        throttler.record_message_sent()

        mock_time.time.return_value = base_time + 30
        throttler.wait_if_needed()
        throttler.record_message_sent()

        mock_time.time.return_value = base_time + 61
        throttler.wait_if_needed()
        throttler.record_message_sent()

        mock_time.sleep.assert_not_called()

    @patch("hl7_sender.message_throttler.time")
    def test_record_message_sent_does_nothing_when_disabled(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(messages_per_minute=None)
        mock_time.time.return_value = 1000.0

        throttler.record_message_sent()

        self.assertEqual(len(throttler._timestamps), 0)

    @patch("hl7_sender.message_throttler.time")
    def test_record_message_sent_adds_timestamp(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(messages_per_minute=10)
        mock_time.time.return_value = 1000.0

        throttler.record_message_sent()

        self.assertEqual(len(throttler._timestamps), 1)
        self.assertEqual(throttler._timestamps[0], 1000.0)


if __name__ == '__main__':
    unittest.main()

