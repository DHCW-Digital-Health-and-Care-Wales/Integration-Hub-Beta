"""
Unit tests for configuration defaults.
Verifies env vars are read correctly with safe fallbacks.
"""
from __future__ import annotations

import importlib
import os
from unittest.mock import patch


class TestConfigDefaults:
    def _load_config(self, env: dict) -> object:
        """Re-import config module with a patched environment."""
        with patch.dict(os.environ, env, clear=True):
            import dashboard.config as cfg
            importlib.reload(cfg)
            return cfg

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

    def test_queue_name_defaults(self) -> None:
        cfg = self._load_config({})
        assert cfg.QUEUE_PHW_PRE == "pre-phw-transform"
        assert cfg.QUEUE_PHW_POST == "post-phw-transform"
        assert cfg.QUEUE_PARIS_PRE == "pre-paris-transform"
        assert cfg.QUEUE_CHEMO_PRE == "pre-chemo-transform"
        assert cfg.QUEUE_PIMS_PRE == "pre-pims-transform"
        assert cfg.QUEUE_MPI_OUTBOUND == "mpi-outbound"

    def test_queue_name_override(self) -> None:
        cfg = self._load_config({"QUEUE_PHW_PRE": "custom-phw-queue"})
        assert cfg.QUEUE_PHW_PRE == "custom-phw-queue"
