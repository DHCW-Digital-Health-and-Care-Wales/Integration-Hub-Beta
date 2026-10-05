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

    def test_reads_environment(self) -> None:
        env = {"LOOKUP_SEED_DIR": "/data/seed", "ENVIRONMENT": "prd", "PORT": "9000", "LOG_LEVEL": "debug"}
        with mock.patch.dict("os.environ", env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.seed_dir, Path("/data/seed"))
        self.assertEqual(settings.environment, "PRD")
        self.assertEqual(settings.port, 9000)
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertFalse(settings.swagger_enabled)

    def test_blank_values_fall_back_to_defaults(self) -> None:
        with mock.patch.dict("os.environ", {"PORT": "  ", "ENVIRONMENT": ""}, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.environment, "DEV")

    def test_invalid_port(self) -> None:
        with mock.patch.dict("os.environ", {"PORT": "eighty"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "PORT must be an integer"):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
