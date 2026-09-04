"""Persist small app-wide preferences (currently just the selected theme)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ultra7.ui.themes import DEFAULT_THEME_NAME

DEFAULT_SETTINGS_PATH = Path.home() / ".ultra7" / "settings.json"


def load_theme_name(path: Path = DEFAULT_SETTINGS_PATH) -> str:
    try:
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except (OSError, ValueError):
        return DEFAULT_THEME_NAME
    return data.get("theme", DEFAULT_THEME_NAME)


def save_theme_name(name: str, path: Path = DEFAULT_SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump({"theme": name}, f, indent=2)
    os.replace(tmp_path, path)
