import os
import unittest
from unittest.mock import patch

from buswatch.config import DEFAULT_CONNECTION_STRING, _parse_queue_names, get_settings


class TestConfigHelpers(unittest.TestCase):
    def test_parse_queue_names_ignores_blanks_and_whitespace(self) -> None:
        queue_names = _parse_queue_names(" alpha, beta ,, gamma , ")

        self.assertEqual(queue_names, ["alpha", "beta", "gamma"])


class TestGetSettings(unittest.TestCase):
    @patch.dict(os.environ, {"BUSWATCH_PEEK_COUNT": "15"}, clear=True)
    @patch("buswatch.config._load_config_file_values")
    def test_get_settings_prefers_environment_values(self, mock_load_config_file_values: unittest.mock.Mock) -> None:
        mock_load_config_file_values.return_value = {
            "SERVICEBUS_CONNECTION_STRING": "config-connection-string",
            "BUSWATCH_QUEUE_NAMES": "queue-a, queue-b",
            "BUSWATCH_PEEK_COUNT": "25",
            "BUSWATCH_DETAIL_SEARCH_LIMIT": "40",
            "BUSWATCH_MAX_PARALLEL_QUEUE_FETCHES": "3",
        }

        settings = get_settings()

        self.assertEqual(settings.servicebus_connection_string, "config-connection-string")
        self.assertEqual(settings.queue_names, ["queue-a", "queue-b"])
        self.assertEqual(settings.peek_count, 15)
        self.assertEqual(settings.detail_search_limit, 40)
        self.assertEqual(settings.max_parallel_queue_fetches, 3)

    @patch.dict(os.environ, {}, clear=True)
    @patch("buswatch.config._load_config_file_values", return_value={})
    def test_get_settings_uses_defaults_when_no_overrides_exist(
        self, mock_load_config_file_values: unittest.mock.Mock
    ) -> None:
        settings = get_settings()

        self.assertEqual(settings.servicebus_connection_string, DEFAULT_CONNECTION_STRING)
        self.assertEqual(settings.queue_names, [])
        self.assertEqual(settings.peek_count, 25)
        self.assertEqual(settings.detail_search_limit, 250)
        self.assertEqual(settings.max_parallel_queue_fetches, 2)


if __name__ == "__main__":
    unittest.main()
