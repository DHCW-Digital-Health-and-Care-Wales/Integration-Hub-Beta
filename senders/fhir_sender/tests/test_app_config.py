import os
import unittest
from unittest.mock import patch

from fhir_sender.app_config import AppConfig

BASE_ENV = {
    "INGRESS_QUEUE_NAME": "q",
    "FHIR_ENDPOINT_URL": "https://example.test/$process-message",
    "WORKFLOW_ID": "w",
    "MICROSERVICE_ID": "m",
    "HEALTH_BOARD": "h",
    "PEER_SERVICE": "p",
}


class AppConfigTests(unittest.TestCase):
    def _read(self, extra: dict[str, str] | None = None) -> AppConfig:
        with patch.dict(os.environ, {**BASE_ENV, **(extra or {})}, clear=True):
            return AppConfig.read_env_config()

    def test_api_key_mode_requires_key(self) -> None:
        with self.assertRaises(RuntimeError):
            self._read()
        config = self._read({"FHIR_API_KEY": "k"})
        self.assertEqual(config.auth_mode, "api_key")
        self.assertEqual(config.max_attempts, 3)
        self.assertIsNone(config.ingress_session_id)

    def test_oauth2_mode_requires_all_oauth_settings(self) -> None:
        partial = {"FHIR_AUTH_MODE": "oauth2", "FHIR_OAUTH_TOKEN_URL": "https://auth.test/token"}
        with self.assertRaises(RuntimeError):
            self._read(partial)
        config = self._read({
            **partial,
            "FHIR_OAUTH_CLIENT_ID": "id",
            "FHIR_OAUTH_CLIENT_SECRET": "secret",
            "FHIR_OAUTH_SCOPE": "target-entity:1",
        })
        self.assertIsNone(config.api_key)

    def test_unknown_auth_mode_and_non_positive_numbers_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._read({"FHIR_AUTH_MODE": "basic"})
        with self.assertRaises(ValueError):
            self._read({"FHIR_API_KEY": "k", "FHIR_MAX_ATTEMPTS": "0"})


if __name__ == "__main__":
    unittest.main()
