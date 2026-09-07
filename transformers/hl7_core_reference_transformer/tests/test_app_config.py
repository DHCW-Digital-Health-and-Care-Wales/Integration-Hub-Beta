"""Tests for WRDSConfig — env-var reading and defaults."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from hl7_core_reference_transformer.app_config import WRDSConfig


class TestWRDSConfig(unittest.TestCase):
    def test_reads_required_and_optional_values(self) -> None:
        env = {
            "WRDS_ENDPOINT_URL": "https://example.test/wrdssoapservice",
            "WRDS_TIMEOUT_SECONDS": "45",
            "WRDS_CLIENT_CERT_PATH": "certs/client.pem",
            "WRDS_LOOKUP_TABLE_NAME": "SomeOtherTable",
            "WRDS_LOCAL_FIXTURE_PATH": "wrds_local_fixture.json",
        }
        with patch.dict(os.environ, env, clear=False):
            config = WRDSConfig.read_env_config()

        self.assertEqual(
            config.endpoint_url, env.get("WRDS_ENDPOINT_URL")
        )
        self.assertEqual(config.timeout_seconds, 45)
        self.assertEqual(config.client_cert_path, "certs/client.pem")
        self.assertEqual(config.lookup_table_name, "SomeOtherTable")
        self.assertEqual(config.local_fixture_path, "wrds_local_fixture.json")

    def test_applies_defaults_when_optional_values_missing(self) -> None:
        env = {"WRDS_ENDPOINT_URL": "https://example.test/wrdssoapservice"}
        with patch.dict(
            os.environ,
            env,
            clear=False,
        ):
            os.environ.pop("WRDS_TIMEOUT_SECONDS", None)
            os.environ.pop("WRDS_CLIENT_CERT_PATH", None)
            os.environ.pop("WRDS_LOOKUP_TABLE_NAME", None)
            os.environ.pop("WRDS_LOCAL_FIXTURE_PATH", None)

            config = WRDSConfig.read_env_config()

        self.assertEqual(config.timeout_seconds, 30)
        self.assertIsNone(config.client_cert_path)
        self.assertEqual(config.lookup_table_name, "FioranoCodeTranslation")
        self.assertIsNone(config.local_fixture_path)

    def test_missing_endpoint_url_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WRDS_ENDPOINT_URL", None)

            with self.assertRaises(ValueError):
                WRDSConfig.read_env_config()


if __name__ == "__main__":
    unittest.main()
