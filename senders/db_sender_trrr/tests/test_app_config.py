from __future__ import annotations

import os
from unittest import mock

from db_sender_trrr.app_config import AppConfig

_BASE_ENV = {
    "INGRESS_TOPIC_NAME": "topic",
    "INGRESS_SUBSCRIPTION_NAME": "sub",
}


def _read(extra: dict[str, str] | None = None) -> AppConfig:
    env = {**_BASE_ENV, **(extra or {})}
    with mock.patch.dict(os.environ, env, clear=True):
        return AppConfig.read_env_config()


def test_default_stored_procedure_is_sp_process_result() -> None:
    assert _read().db_stored_procedure == "dbo.spProcessResult"


def test_explicit_stored_procedure_overrides_default() -> None:
    config = _read({"DB_STORED_PROCEDURE": "dbo.Custom"})

    assert config.db_stored_procedure == "dbo.Custom"


def test_legacy_mapping_type_variable_is_ignored() -> None:
    # One sender now handles both request types; a leftover TRRR_MAPPING_TYPE must not break start-up.
    assert _read({"TRRR_MAPPING_TYPE": "BOGUS"}).db_stored_procedure == "dbo.spProcessResult"
