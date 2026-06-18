"""
Unit tests for configuration defaults.
Verifies env vars are read correctly with safe fallbacks.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import patch

import dashboard.config as _cfg_module


class TestConfigDefaults:
    def _load_config(self, env: dict) -> types.ModuleType:
        """Re-import config module with a patched environment."""
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            importlib.reload(_cfg_module)
            return _cfg_module

    def teardown_method(self) -> None:
        """Restore config module to real environment after each test."""
        importlib.reload(_cfg_module)

    def test_warning_threshold_default(self) -> None:
        cfg = self._load_config({})
        assert cfg.QUEUE_WARNING_THRESHOLD == 10

    def test_critical_threshold_default(self) -> None:
        cfg = self._load_config({})
        assert cfg.QUEUE_CRITICAL_THRESHOLD == 50

    def test_dlq_threshold_default(self) -> None:
        cfg = self._load_config({})
        assert cfg.DLQ_WARNING_THRESHOLD == 1

    def test_cache_ttl_default(self) -> None:
        cfg = self._load_config({})
        assert cfg.API_CACHE_TTL == 30

    def test_warning_threshold_override(self) -> None:
        cfg = self._load_config({"QUEUE_WARNING_THRESHOLD": "25"})
        assert cfg.QUEUE_WARNING_THRESHOLD == 25


class TestEnvironmentLabel:
    """Tests for ENVIRONMENT_LABEL parsing from AZURE_RESOURCE_GROUP."""

    def _load_config(self, env: dict) -> types.ModuleType:
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            importlib.reload(_cfg_module)
            return _cfg_module

    def teardown_method(self) -> None:
        importlib.reload(_cfg_module)

    # --- Parsing ---

    def test_standard_env_extracted(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-TST-App-RG"})
        assert cfg._raw_environment == "TST"

    def test_uk_west_prefix_extracted(self) -> None:
        # DR uses UK-West rather than UK-South
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-West-DHCW-IntHub-DR-App-RG"})
        assert cfg._raw_environment == "DR"

    def test_all_standard_env_codes_parsed(self) -> None:
        for code in ("DEV", "TST", "UAT", "DTE", "LOAD", "PPD", "PRD"):
            cfg = self._load_config({"AZURE_RESOURCE_GROUP": f"UK-South-DHCW-IntHub-{code}-App-RG"})
            assert cfg._raw_environment == code

    def test_empty_resource_group_gives_empty_label(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": ""})
        assert cfg.ENVIRONMENT_LABEL == ""

    def test_non_matching_resource_group_gives_empty_label(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "some-unrelated-rg"})
        assert cfg.ENVIRONMENT_LABEL == ""

    def test_missing_resource_group_gives_empty_label(self) -> None:
        cfg = self._load_config({})
        assert cfg.ENVIRONMENT_LABEL == ""

    # --- ENVIRONMENT_LABEL_MAP overrides ---

    def test_label_map_overrides_raw_code(self) -> None:
        cfg = self._load_config(
            {
                "AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-TST-App-RG",
                "ENVIRONMENT_LABEL_MAP": "TST:TESTING",
            }
        )
        assert cfg.ENVIRONMENT_LABEL == "TESTING"

    def test_label_map_multi_entry(self) -> None:
        cfg = self._load_config(
            {
                "AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-PRD-App-RG",
                "ENVIRONMENT_LABEL_MAP": "TST:TESTING,PRD:PRODUCTION",
            }
        )
        assert cfg.ENVIRONMENT_LABEL == "PRODUCTION"

    def test_label_map_missing_code_falls_back_to_raw(self) -> None:
        # UAT not in map — should fall back to "UAT"
        cfg = self._load_config(
            {
                "AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-UAT-App-RG",
                "ENVIRONMENT_LABEL_MAP": "TST:TESTING",
            }
        )
        assert cfg.ENVIRONMENT_LABEL == "UAT"

    def test_empty_label_map_falls_back_to_raw(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-TST-App-RG"})
        assert cfg.ENVIRONMENT_LABEL == "TST"


class TestEnvironmentColour:
    """Tests for ENVIRONMENT_COLOR resolution."""

    def _load_config(self, env: dict) -> types.ModuleType:
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            importlib.reload(_cfg_module)
            return _cfg_module

    def teardown_method(self) -> None:
        importlib.reload(_cfg_module)

    # --- _resolve_colour ---

    def test_resolve_known_colour_name(self) -> None:
        cfg = self._load_config({})
        assert cfg._resolve_colour("green") == "#22c55e"

    def test_resolve_colour_name_case_insensitive(self) -> None:
        cfg = self._load_config({})
        assert cfg._resolve_colour("Purple") == "#a855f7"
        assert cfg._resolve_colour("RED") == "#ef4444"

    def test_resolve_orange_alias(self) -> None:
        cfg = self._load_config({})
        assert cfg._resolve_colour("orange") == "#f59e0b"

    def test_resolve_grey_and_gray_aliases(self) -> None:
        cfg = self._load_config({})
        assert cfg._resolve_colour("grey") == cfg._resolve_colour("gray")

    def test_resolve_raw_hex_passthrough(self) -> None:
        cfg = self._load_config({})
        assert cfg._resolve_colour("#c026d3") == "#c026d3"

    def test_resolve_unknown_name_returns_grey_fallback(self) -> None:
        cfg = self._load_config({})
        assert cfg._resolve_colour("pink") == "#94a3b8"

    # --- Built-in defaults ---

    def test_default_colour_tst_is_purple(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-TST-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#a855f7"

    def test_default_colour_dev_is_green(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-DEV-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#22c55e"

    def test_default_colour_prd_is_red(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-PRD-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#ef4444"

    def test_default_colour_ppd_is_red(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-PPD-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#ef4444"

    def test_default_colour_dte_is_green(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-DTE-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#22c55e"

    def test_default_colour_uat_is_amber(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-UAT-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#f59e0b"

    def test_default_colour_load_is_cyan(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-LOAD-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#06b6d4"

    def test_default_colour_dr_is_amber(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-West-DHCW-IntHub-DR-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#f59e0b"

    # --- ENVIRONMENT_COLOR_MAP overrides ---

    def test_color_map_name_override(self) -> None:
        cfg = self._load_config(
            {
                "AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-TST-App-RG",
                "ENVIRONMENT_COLOR_MAP": "TST:blue",
            }
        )
        assert cfg.ENVIRONMENT_COLOR == "#3b82f6"

    def test_color_map_raw_hex_override(self) -> None:
        cfg = self._load_config(
            {
                "AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-TST-App-RG",
                "ENVIRONMENT_COLOR_MAP": "TST:#ff00ff",
            }
        )
        assert cfg.ENVIRONMENT_COLOR == "#ff00ff"

    def test_color_map_missing_code_uses_default(self) -> None:
        # PRD not in map — should still get the built-in red default
        cfg = self._load_config(
            {
                "AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-PRD-App-RG",
                "ENVIRONMENT_COLOR_MAP": "TST:blue",
            }
        )
        assert cfg.ENVIRONMENT_COLOR == "#ef4444"

    def test_unknown_env_code_with_no_default_returns_grey(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": "UK-South-DHCW-IntHub-XYZ-App-RG"})
        assert cfg.ENVIRONMENT_COLOR == "#94a3b8"

    def test_empty_resource_group_colour_is_grey(self) -> None:
        cfg = self._load_config({"AZURE_RESOURCE_GROUP": ""})
        assert cfg.ENVIRONMENT_COLOR == "#94a3b8"
