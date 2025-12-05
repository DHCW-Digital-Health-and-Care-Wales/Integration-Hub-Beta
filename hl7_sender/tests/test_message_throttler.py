import unittest
from unittest.mock import patch

from hl7_sender.message_throttler import MessageThrottler


class TestMessageThrottler(unittest.TestCase):

    def test_no_throttling_when_disabled(self) -> None:
        throttler = MessageThrottler(max_messages_per_minute=None)

        with patch("hl7_sender.message_throttler.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            for _ in range(100):
                throttler.wait_if_needed()

            mock_time.sleep.assert_not_called()

    @patch("hl7_sender.message_throttler.time")
    def test_first_message_not_throttled(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(max_messages_per_minute=30)
        mock_time.monotonic.return_value = 1000.0

        throttler.wait_if_needed()

        mock_time.sleep.assert_not_called()

    @patch("hl7_sender.message_throttler.time")
    def test_throttles_when_interval_not_elapsed(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(max_messages_per_minute=30)  # 2 seconds between messages

        mock_time.monotonic.side_effect = [1000.0, 1000.5, 1002.0]
        throttler.wait_if_needed()  # sets last_message_time to 1000.0

        throttler.wait_if_needed()

        mock_time.sleep.assert_called_once()
        sleep_duration = mock_time.sleep.call_args[0][0]
        self.assertAlmostEqual(sleep_duration, 1.5, places=1)  # Should wait 1.5 more seconds

    @patch("hl7_sender.message_throttler.time")
    def test_no_throttle_when_interval_elapsed(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(max_messages_per_minute=30)  # 2 seconds between messages

        mock_time.monotonic.side_effect = [1000.0, 1002.5]
        throttler.wait_if_needed()  # sets last_message_time to 1000.0

        throttler.wait_if_needed()

        mock_time.sleep.assert_not_called()

    @patch("hl7_sender.message_throttler.time")
    def test_throttle_calculates_correct_wait_time(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(max_messages_per_minute=60)  # 1 second between messages

        mock_time.monotonic.side_effect = [1000.0, 1000.3, 1001.0]
        throttler.wait_if_needed()  # sets last_message_time to 1000.0

        throttler.wait_if_needed()

        mock_time.sleep.assert_called_once()
        sleep_duration = mock_time.sleep.call_args[0][0]
        self.assertAlmostEqual(sleep_duration, 0.7, places=1)

    @patch("hl7_sender.message_throttler.time")
    def test_multiple_messages_at_correct_rate(self, mock_time: unittest.mock.Mock) -> None:
        throttler = MessageThrottler(max_messages_per_minute=30)  # 2 seconds between messages

        mock_time.monotonic.side_effect = [1000.0, 1001.0, 1002.0, 1004.0]
        throttler.wait_if_needed()  # sets last_message_time to 1000.0
        mock_time.sleep.assert_not_called()

        throttler.wait_if_needed()
        mock_time.sleep.assert_called_once()
        self.assertAlmostEqual(mock_time.sleep.call_args[0][0], 1.0, places=1)
        mock_time.sleep.reset_mock()

        throttler.wait_if_needed()
        mock_time.sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
