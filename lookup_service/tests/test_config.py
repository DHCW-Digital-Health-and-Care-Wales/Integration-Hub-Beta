from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from lookup_service.config import DEFAULT_SEED_DIR, Settings


class SettingsTests(unittest.TestCase):
    def test_defaults(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.seed_dir, DEFAULT_SEED_DIR)
        self.assertEqual(settings.environment, "DEV")
        self.assertEqual(settings.port, 8080)
        self.assertTrue(settings.swagger_enabled)
        self.assertFalse(settings.writes_enabled)
        self.assertIsNone(settings.cosmos_endpoint)
        self.assertEqual((settings.rows_container, settings.config_container), ("lookup-rows", "lookup-config"))
        self.assertEqual(settings.default_ttl_seconds, 300)
        self.assertEqual(settings.max_upload_bytes, 50 * 1024 * 1024)

    def test_reads_environment(self) -> None:
        env = {
            "LOOKUP_SEED_DIR": "/data/seed", "ENVIRONMENT": "local", "PORT": "9000", "LOG_LEVEL": "debug",
            "COSMOS_ENDPOINT": "https://localhost:8081", "COSMOS_KEY": "k", "COSMOS_DATABASE": "db",
            "COSMOS_DISABLE_SSL_VERIFY": "TRUE", "LOOKUP_ROWS_CONTAINER": "r", "LOOKUP_CONFIG_CONTAINER": "c",
            "LOOKUP_DEFAULT_TTL_SECONDS": "60", "LOOKUP_MAX_UPLOAD_MB": "5", "LOOKUP_CACHE_MAX_ENTRIES": "7",
            "LOOKUP_UPLOAD_CONCURRENCY": "4",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.seed_dir, Path("/data/seed"))
        self.assertEqual(settings.environment, "LOCAL")
        self.assertTrue(settings.writes_enabled)
        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.cosmos_endpoint, "https://localhost:8081")
        self.assertTrue(settings.cosmos_disable_ssl_verify)
        self.assertEqual((settings.cosmos_database, settings.rows_container, settings.config_container),
                         ("db", "r", "c"))
        self.assertEqual((settings.default_ttl_seconds, settings.max_upload_mb, settings.cache_max_entries,
                          settings.upload_concurrency), (60, 5, 7, 4))

    def test_production_has_no_swagger_and_no_writes(self) -> None:
        with mock.patch.dict("os.environ", {"ENVIRONMENT": "prd"}, clear=True):
            settings = Settings.from_env()
        self.assertFalse(settings.swagger_enabled)
        self.assertFalse(settings.writes_enabled)

    def test_blank_values_fall_back_to_defaults(self) -> None:
        with mock.patch.dict("os.environ", {"PORT": "  ", "ENVIRONMENT": ""}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.environment, "DEV")

    def test_invalid_integers(self) -> None:
        for env, message in (({"PORT": "eighty"}, "PORT must be an integer"),
                             ({"LOOKUP_DEFAULT_TTL_SECONDS": "0"}, "must be >= 1")):
            with self.subTest(env=env), mock.patch.dict("os.environ", env, clear=True):
                with self.assertRaisesRegex(RuntimeError, message):
                    Settings.from_env()

    def test_ssl_verification_can_only_be_disabled_for_the_emulator(self) -> None:
        env = {"COSMOS_ENDPOINT": "https://prod-account.documents.azure.com:443/", "COSMOS_DISABLE_SSL_VERIFY": "true"}
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "only allowed for a local Cosmos emulator"):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
