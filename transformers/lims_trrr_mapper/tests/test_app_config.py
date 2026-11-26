from __future__ import annotations

import os
import unittest
from unittest import mock

from lims_trrr_mapper.app_config import AppConfig

BASE_ENV = {
    "INGRESS_TOPIC_NAME": "local-inthub-lims-hl7-input",
    "INGRESS_SUBSCRIPTION_NAME": "local-inthub-lims-trrr-nhsid-mapper-sub",
    "INGRESS_SESSION_ID": "lims-soapserver",
    "EGRESS_TOPIC_NAME": "local-inthub-lims-trrr-mapped",
    "EGRESS_SESSION_ID": "lims-trrr-mapped",
    "TRRR_MAPPING_TYPE": "NHS_ID_UPDATE",
}


class TestAppConfig(unittest.TestCase):
    def _read(self, **overrides: str) -> AppConfig:
        env = {**BASE_ENV, **overrides}
        with mock.patch.dict(os.environ, env, clear=True):
            return AppConfig.read_env_config()

    def test_reads_ingress_and_egress_settings(self) -> None:
        config = self._read()

        self.assertEqual(config.ingress_topic_name, "local-inthub-lims-hl7-input")
        self.assertEqual(config.ingress_session_id, "lims-soapserver")
        self.assertEqual(config.egress_topic_name, "local-inthub-lims-trrr-mapped")
        self.assertEqual(config.egress_session_id, "lims-trrr-mapped")
        self.assertEqual(config.mapping_type, "NHS_ID_UPDATE")
        self.assertEqual(config.max_batch_size, 10)

    def test_mapping_type_is_case_insensitive(self) -> None:
        self.assertEqual(self._read(TRRR_MAPPING_TYPE=" merge ").mapping_type, "MERGE")

    def test_mapping_type_is_required(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "TRRR_MAPPING_TYPE"):
            self._read(TRRR_MAPPING_TYPE="")

    def test_rejects_unknown_mapping_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid TRRR_MAPPING_TYPE"):
            self._read(TRRR_MAPPING_TYPE="DELETE")

    def test_egress_session_id_is_required(self) -> None:
        # Without it the published requests could never be received by the session-locked senders.
        with self.assertRaisesRegex(RuntimeError, "EGRESS_SESSION_ID"):
            self._read(EGRESS_SESSION_ID=" ")

    def test_egress_topic_is_required(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "EGRESS_TOPIC_NAME"):
            self._read(EGRESS_TOPIC_NAME="")

    def test_rejects_non_integer_batch_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "MAX_BATCH_SIZE"):
            self._read(MAX_BATCH_SIZE="ten")


if __name__ == "__main__":
    unittest.main()
