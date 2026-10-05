import os
import unittest
from unittest.mock import patch

from hl7_topic_mock_receiver.app_config import AppConfig


class TestAppConfig(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_read_env_config_with_no_env_vars_does_not_raise(self) -> None:
        config = AppConfig.read_env_config()

        self.assertIsNone(config.egress_topic_name)
        self.assertFalse(config.service_bus_enabled)

    @patch.dict(
        os.environ,
        {
            "EGRESS_TOPIC_NAME": "egress-topic",
            "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
        },
        clear=True,
    )
    def test_service_bus_enabled_when_topic_and_connection_string_present(self) -> None:
        config = AppConfig.read_env_config()

        self.assertTrue(config.service_bus_enabled)

    @patch.dict(os.environ, {"EGRESS_TOPIC_NAME": "egress-topic"}, clear=True)
    def test_service_bus_disabled_when_topic_set_but_no_connection_info(self) -> None:
        config = AppConfig.read_env_config()

        self.assertFalse(config.service_bus_enabled)


if __name__ == "__main__":
    unittest.main()
