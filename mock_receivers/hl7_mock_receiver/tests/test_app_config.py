import os
import unittest
from unittest.mock import patch

from hl7_mock_receiver.app_config import AppConfig


class TestAppConfig(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_read_env_config_with_no_env_vars_does_not_raise(self) -> None:
        config = AppConfig.read_env_config()

        self.assertIsNone(config.egress_queue_name)
        self.assertFalse(config.service_bus_enabled)

    @patch.dict(
        os.environ,
        {
            "EGRESS_QUEUE_NAME": "egress-queue",
            "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
        },
        clear=True,
    )
    def test_service_bus_enabled_when_queue_and_connection_string_present(self) -> None:
        config = AppConfig.read_env_config()

        self.assertTrue(config.service_bus_enabled)

    @patch.dict(os.environ, {"EGRESS_QUEUE_NAME": "egress-queue"}, clear=True)
    def test_service_bus_disabled_when_queue_set_but_no_connection_info(self) -> None:
        config = AppConfig.read_env_config()

        self.assertFalse(config.service_bus_enabled)


if __name__ == "__main__":
    unittest.main()
