from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from lookup_service.config import DEFAULT_SEED_DIR, Settings

AUTH_ENV = {"LOOKUP_AUTH_TENANT_ID": "tenant", "LOOKUP_AUTH_AUDIENCE": "api://lookup"}


class SettingsTests(unittest.TestCase):
    def test_defaults(self) -> None:
        with mock.patch.dict("os.environ", AUTH_ENV, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.seed_dir, DEFAULT_SEED_DIR)
        self.assertEqual(settings.environment, "DEV")
        self.assertEqual(settings.port, 8080)
        self.assertTrue(settings.swagger_enabled)
        self.assertTrue(settings.auth_enabled)
        self.assertEqual((settings.auth_tenant_id, settings.auth_audience), ("tenant", "api://lookup"))
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
            "LOOKUP_UPLOAD_CONCURRENCY": "4", "LOOKUP_AUTH_DISABLED": "true",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.seed_dir, Path("/data/seed"))
        self.assertEqual(settings.environment, "LOCAL")
        self.assertTrue(settings.auth_disabled)
        self.assertFalse(settings.auth_enabled)
        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.cosmos_endpoint, "https://localhost:8081")
        self.assertTrue(settings.cosmos_disable_ssl_verify)
        self.assertEqual((settings.cosmos_database, settings.rows_container, settings.config_container),
                         ("db", "r", "c"))
        self.assertEqual((settings.default_ttl_seconds, settings.max_upload_mb, settings.cache_max_entries,
                          settings.upload_concurrency), (60, 5, 7, 4))

    def test_production_has_no_swagger(self) -> None:
        with mock.patch.dict("os.environ", {**AUTH_ENV, "ENVIRONMENT": "prd"}, clear=True):
            settings = Settings.from_env()
        self.assertFalse(settings.swagger_enabled)

    def test_blank_values_fall_back_to_defaults(self) -> None:
        with mock.patch.dict("os.environ", {**AUTH_ENV, "PORT": "  ", "ENVIRONMENT": ""}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.environment, "DEV")

    def test_invalid_integers(self) -> None:
        for env, message in (({"PORT": "eighty"}, "PORT must be an integer"),
                             ({"LOOKUP_DEFAULT_TTL_SECONDS": "0"}, "must be >= 1")):
            with self.subTest(env=env), mock.patch.dict("os.environ", {**AUTH_ENV, **env}, clear=True):
                with self.assertRaisesRegex(RuntimeError, message):
                    Settings.from_env()

    def test_ssl_verification_can_only_be_disabled_for_the_emulator(self) -> None:
        env = {**AUTH_ENV, "COSMOS_ENDPOINT": "https://prod-account.documents.azure.com:443/",
               "COSMOS_DISABLE_SSL_VERIFY": "true"}
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "only allowed for a local Cosmos emulator"):
                Settings.from_env()


class AuthSettingsTests(unittest.TestCase):
    def test_missing_auth_configuration_refuses_to_start(self) -> None:
        for env in ({}, {"ENVIRONMENT": "PRD"}, {"LOOKUP_AUTH_TENANT_ID": "t"}, {"LOOKUP_AUTH_AUDIENCE": "a"},
                    {"ENVIRONMENT": "LOCAL"}):
            with self.subTest(env=env), mock.patch.dict("os.environ", env, clear=True):
                with self.assertRaisesRegex(RuntimeError, "Authentication is not configured"):
                    Settings.from_env()

    def test_auth_cannot_be_disabled_outside_local(self) -> None:
        for environment in ("DEV", "TST", "PRD"):
            env = {**AUTH_ENV, "ENVIRONMENT": environment, "LOOKUP_AUTH_DISABLED": "true"}
            with self.subTest(environment=environment), mock.patch.dict("os.environ", env, clear=True):
                with self.assertRaisesRegex(RuntimeError, "only allowed when ENVIRONMENT=LOCAL"):
                    Settings.from_env()

    def test_disabled_auth_is_accepted_locally_without_configuration(self) -> None:
        with mock.patch.dict("os.environ", {"ENVIRONMENT": "local", "LOOKUP_AUTH_DISABLED": "true"}, clear=True):
            settings = Settings.from_env()
        self.assertFalse(settings.auth_enabled)

    def test_auth_disabled_must_be_a_boolean(self) -> None:
        env = {"ENVIRONMENT": "LOCAL", "LOOKUP_AUTH_DISABLED": "maybe"}
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "LOOKUP_AUTH_DISABLED must be true or false"):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
