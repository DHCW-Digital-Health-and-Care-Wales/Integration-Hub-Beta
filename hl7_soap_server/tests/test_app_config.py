import os
import unittest
from unittest.mock import patch

from hl7_soap_server.app_config import DEFAULT_MAX_REQUEST_SIZE_BYTES, AppConfig

BASE_ENV = {
    "EGRESS_QUEUE_NAME": "egress-queue",
    "EGRESS_SESSION_ID": "soap-session",
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
    "MESSAGE_STORE_QUEUE_NAME": "message-store",
    "WORKFLOW_ID": "workflow-soap",
    "MICROSERVICE_ID": "hl7-soap-server",
    "HEALTH_BOARD": "test-board",
    "PEER_SERVICE": "hl7-sender",
}


class TestAppConfig(unittest.TestCase):
    @patch.dict(os.environ, BASE_ENV, clear=True)
    def test_read_env_config_defaults(self) -> None:
        config = AppConfig.read_env_config()
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.soap_endpoint_path, "/soap")
        self.assertEqual(config.schema_group, "phw")
        self.assertEqual(config.allowed_hl7_structures, ["ADT_A05", "ADT_A39"])
        self.assertEqual(config.allowed_assigning_authorities, ["328"])
        self.assertEqual(config.max_request_size_bytes, DEFAULT_MAX_REQUEST_SIZE_BYTES)

    @patch.dict(
        os.environ,
        {
            **BASE_ENV,
            "SOAP_ENDPOINT_PATH": "soap",
        },
        clear=True,
    )
    def test_invalid_endpoint_path_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()

    @patch.dict(
        os.environ,
        {
            **BASE_ENV,
            "MAX_REQUEST_SIZE_BYTES": str(104857601),
        },
        clear=True,
    )
    def test_request_size_above_service_bus_limit_raises(self) -> None:
        with self.assertRaises(ValueError):
            AppConfig.read_env_config()

    @patch.dict(
        os.environ,
        {
            **BASE_ENV,
            "EGRESS_TOPIC_NAME": "egress-topic",
        },
        clear=True,
    )
    def test_cannot_configure_both_queue_and_topic(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()
