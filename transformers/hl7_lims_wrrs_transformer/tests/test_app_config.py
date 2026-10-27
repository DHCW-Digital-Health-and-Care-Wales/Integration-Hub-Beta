from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from hl7_lims_wrrs_transformer.app_config import MappingTypeConfig


class TestMappingTypeConfig(unittest.TestCase):
    def test_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = MappingTypeConfig.read_env_config()

        self.assertEqual(config.nhs_id_update, "LIMS_NHS_ID_UPDATE")
        self.assertEqual(config.a40, "ADT_A40")

    def test_env_overrides(self) -> None:
        env = {"MAPPING_TYPE_NHS_ID_UPDATE": "CUSTOM_NHS", "MAPPING_TYPE_A40": "CUSTOM_A40"}
        with patch.dict(os.environ, env, clear=True):
            config = MappingTypeConfig.read_env_config()

        self.assertEqual(config, MappingTypeConfig(nhs_id_update="CUSTOM_NHS", a40="CUSTOM_A40"))

    def test_blank_override_falls_back_to_default(self) -> None:
        with patch.dict(os.environ, {"MAPPING_TYPE_A40": "   "}, clear=True):
            self.assertEqual(MappingTypeConfig.read_env_config().a40, "ADT_A40")

    def test_identical_values_are_rejected(self) -> None:
        env = {"MAPPING_TYPE_NHS_ID_UPDATE": "SAME", "MAPPING_TYPE_A40": "SAME"}
        with patch.dict(os.environ, env, clear=True), self.assertRaises(ValueError):
            MappingTypeConfig.read_env_config()


if __name__ == "__main__":
    unittest.main()
