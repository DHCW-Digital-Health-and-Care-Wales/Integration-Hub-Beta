from __future__ import annotations

import os
from unittest import mock

import pytest

from db_sender_trrr.app_config import AppConfig

_BASE_ENV = {
    "INGRESS_TOPIC_NAME": "topic",
    "INGRESS_SUBSCRIPTION_NAME": "sub",
}


def _read(extra: dict[str, str] | None = None) -> AppConfig:
    env = {**_BASE_ENV, **(extra or {})}
    with mock.patch.dict(os.environ, env, clear=True):
        return AppConfig.read_env_config()


def test_default_mapping_type_uses_update_procedure() -> None:
    config = _read()

    assert config.mapping_type == "NHS_ID_UPDATE"
    assert config.db_stored_procedure == "dbo.TRRRIDUpdate"


def test_merge_mapping_type_defaults_to_merge_procedure() -> None:
    config = _read({"TRRR_MAPPING_TYPE": "merge"})

    assert config.mapping_type == "MERGE"
    assert config.db_stored_procedure == "dbo.TRRRIDMerge"


def test_explicit_stored_procedure_overrides_default() -> None:
    config = _read({"TRRR_MAPPING_TYPE": "MERGE", "DB_STORED_PROCEDURE": "dbo.Custom"})

    assert config.db_stored_procedure == "dbo.Custom"


def test_invalid_mapping_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid TRRR_MAPPING_TYPE"):
        _read({"TRRR_MAPPING_TYPE": "BOGUS"})
