import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

from rest_server.app_config import DEFAULT_MAX_REQUEST_SIZE_BYTES, AppConfig

BASE_ENV = {
    "EGRESS_QUEUE_NAME": "egress-queue",
    "EGRESS_SESSION_ID": "rest-session",
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://localhost",
    "MESSAGE_STORE_QUEUE_NAME": "message-store",
    "WORKFLOW_ID": "workflow-rest",
    "MICROSERVICE_ID": "rest-server",
    "HEALTH_BOARD": "test-board",
    "PEER_SERVICE": "hl7-sender",
    "CONTENT_ADAPTER": "xml-raw",
    "VALIDATOR_TYPE": "none",
    "OUTPUT_FORMAT": "raw",
}


class TestAppConfig(unittest.TestCase):
    @patch.dict(os.environ, BASE_ENV, clear=True)
    def test_read_env_config_defaults(self) -> None:
        config = AppConfig.read_env_config()
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.endpoint_path, "/ingest")
        self.assertEqual(config.allowed_hl7_structures, ["ADT_A05", "ADT_A39"])
        self.assertEqual(config.allowed_source_identifiers, [])
        self.assertIsNone(config.source_identifier_locator)
        self.assertEqual(config.max_request_size_bytes, DEFAULT_MAX_REQUEST_SIZE_BYTES)

    @patch.dict(os.environ, {**BASE_ENV, "ENDPOINT_PATH": "ingest"}, clear=True)
    def test_invalid_endpoint_path_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()

    @patch.dict(os.environ, {**BASE_ENV, "CONTENT_ADAPTER": "carrier-pigeon"}, clear=True)
    def test_invalid_content_adapter_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()

    @patch.dict(os.environ, {**BASE_ENV, "VALIDATOR_TYPE": "vibes"}, clear=True)
    def test_invalid_validator_type_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()

    @patch.dict(os.environ, {**BASE_ENV, "OUTPUT_FORMAT": "csv"}, clear=True)
    def test_invalid_output_format_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()

    @patch.dict(os.environ, {k: v for k, v in BASE_ENV.items() if k != "CONTENT_ADAPTER"}, clear=True)
    def test_missing_content_adapter_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()

    @patch.dict(os.environ, {**BASE_ENV, "VALIDATOR_TYPE": "hl7-xsd"}, clear=True)
    def test_hl7_xsd_validator_requires_validation_schema(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()

    @patch.dict(
        os.environ,
        {**BASE_ENV, "VALIDATOR_TYPE": "xsd", "VALIDATION_SCHEMA": "/schemas/partner.xsd"},
        clear=True,
    )
    def test_xsd_validator_accepts_schema_file_path(self) -> None:
        config = AppConfig.read_env_config()
        self.assertEqual(config.validation_schema, "/schemas/partner.xsd")

    @patch.dict(
        os.environ,
        {**BASE_ENV, "SOURCE_IDENTIFIER_LOCATOR": "Header/SourceSystem"},
        clear=True,
    )
    def test_source_identifier_locator_is_split_on_slash(self) -> None:
        config = AppConfig.read_env_config()
        self.assertEqual(config.source_identifier_locator, ["Header", "SourceSystem"])

    @patch.dict(os.environ, {**BASE_ENV, "MAX_REQUEST_SIZE_BYTES": str(104857601)}, clear=True)
    def test_request_size_above_service_bus_limit_raises(self) -> None:
        with self.assertRaises(ValueError):
            AppConfig.read_env_config()

    @patch.dict(os.environ, {**BASE_ENV, "EGRESS_TOPIC_NAME": "egress-topic"}, clear=True)
    def test_cannot_configure_both_queue_and_topic(self) -> None:
        with self.assertRaises(RuntimeError):
            AppConfig.read_env_config()


class TestDotenvLoading(unittest.TestCase):
    """Verifies the .env loading semantics app_config.py relies on at import time.

    ``load_dotenv(..., override=False)`` must only fill in variables absent from the real
    environment - never overriding a value already set by a shell, pipeline or Container Apps -
    and must be a safe no-op when no .env file exists (e.g. every production container).
    """

    def test_dotenv_only_fills_in_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text("REST_SERVER_TEST_FROM_FILE=from-file\nREST_SERVER_TEST_PRESET=from-file\n")

            with patch.dict(os.environ, {"REST_SERVER_TEST_PRESET": "pre-set"}, clear=False):
                os.environ.pop("REST_SERVER_TEST_FROM_FILE", None)
                try:
                    load_dotenv(env_file, override=False)
                    self.assertEqual(os.environ["REST_SERVER_TEST_FROM_FILE"], "from-file")
                    self.assertEqual(os.environ["REST_SERVER_TEST_PRESET"], "pre-set")
                finally:
                    os.environ.pop("REST_SERVER_TEST_FROM_FILE", None)

    def test_missing_dotenv_file_is_a_no_op(self) -> None:
        # Loading a non-existent file must not raise - this is what keeps production
        # containers (which never bake in a .env file) working unchanged.
        load_dotenv(Path("/does/not/exist/.env"), override=False)


if __name__ == "__main__":
    unittest.main()
