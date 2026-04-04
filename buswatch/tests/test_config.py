"""Tests for BusWatch configuration handling."""

from __future__ import annotations

from pathlib import Path

import buswatch.config as config_module
from buswatch.config import get_settings



def test_get_settings_parses_queue_names(monkeypatch) -> None:
    monkeypatch.setenv("BUSWATCH_QUEUE_NAMES", "queue-a, queue-b , ,queue-c")
    monkeypatch.setenv("BUSWATCH_PEEK_COUNT", "10")
    monkeypatch.setenv("BUSWATCH_DETAIL_SEARCH_LIMIT", "99")

    settings = get_settings()

    assert settings.queue_names == ["queue-a", "queue-b", "queue-c"]
    assert settings.peek_count == 10
    assert settings.detail_search_limit == 99



def test_get_settings_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BUSWATCH_QUEUE_NAMES", raising=False)
    monkeypatch.delenv("BUSWATCH_PEEK_COUNT", raising=False)
    monkeypatch.delenv("BUSWATCH_DETAIL_SEARCH_LIMIT", raising=False)
    monkeypatch.delenv("SERVICEBUS_CONNECTION_STRING", raising=False)
    monkeypatch.setattr(config_module, "CONFIG_FILE_PATH", tmp_path / "missing-config.ini")

    settings = get_settings()

    assert settings.queue_names == []
    assert settings.peek_count == 25
    assert settings.detail_search_limit == 250
    assert "UseDevelopmentEmulator=true" in settings.servicebus_connection_string
