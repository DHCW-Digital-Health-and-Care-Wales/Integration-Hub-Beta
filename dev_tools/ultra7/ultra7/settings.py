"""Persist app-wide preferences (theme, fonts, font sizes, and editor behaviour)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ultra7.ui.themes import DEFAULT_THEME_NAME

DEFAULT_SETTINGS_PATH = Path.home() / ".ultra7" / "settings.json"

DefaultLeftView = Literal["messages", "structure"]

MIN_UI_FONT_SIZE = 8
MAX_UI_FONT_SIZE = 20
MIN_EDITOR_FONT_SIZE = 8
MAX_EDITOR_FONT_SIZE = 28
MIN_LOG_FONT_SIZE = 8
MAX_LOG_FONT_SIZE = 24
MIN_TREE_ROW_HEIGHT = 18
MAX_TREE_ROW_HEIGHT = 40


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


@dataclass
class AppPreferences:
    """User-configurable appearance and editor preferences persisted to settings.json."""

    theme: str = DEFAULT_THEME_NAME
    ui_font_family: str = "Rubik"
    ui_font_size: int = 10
    editor_font_family: str = "Menlo"
    editor_font_size: int = 11
    log_font_size: int = 10
    editor_word_wrap: bool = False
    tree_row_height: int = 24
    default_left_view: DefaultLeftView = "messages"
    auto_expand_structure: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "ui_font_family": self.ui_font_family,
            "ui_font_size": self.ui_font_size,
            "editor_font_family": self.editor_font_family,
            "editor_font_size": self.editor_font_size,
            "log_font_size": self.log_font_size,
            "editor_word_wrap": self.editor_word_wrap,
            "tree_row_height": self.tree_row_height,
            "default_left_view": self.default_left_view,
            "auto_expand_structure": self.auto_expand_structure,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppPreferences:
        defaults = cls()
        raw_left = data.get("default_left_view", defaults.default_left_view)
        left_view: DefaultLeftView = "structure" if raw_left == "structure" else "messages"
        ui_family = str(data.get("ui_font_family") or defaults.ui_font_family).strip() or defaults.ui_font_family
        ed_family = (
            str(data.get("editor_font_family") or defaults.editor_font_family).strip()
            or defaults.editor_font_family
        )
        theme_name = str(data.get("theme") or DEFAULT_THEME_NAME)
        return cls(
            theme=theme_name,
            ui_font_family=ui_family,
            ui_font_size=_clamp_int(
                data.get("ui_font_size"), defaults.ui_font_size, MIN_UI_FONT_SIZE, MAX_UI_FONT_SIZE
            ),
            editor_font_family=ed_family,
            editor_font_size=_clamp_int(
                data.get("editor_font_size"), defaults.editor_font_size, MIN_EDITOR_FONT_SIZE, MAX_EDITOR_FONT_SIZE
            ),
            log_font_size=_clamp_int(
                data.get("log_font_size"), defaults.log_font_size, MIN_LOG_FONT_SIZE, MAX_LOG_FONT_SIZE
            ),
            editor_word_wrap=bool(data.get("editor_word_wrap", defaults.editor_word_wrap)),
            tree_row_height=_clamp_int(
                data.get("tree_row_height"), defaults.tree_row_height, MIN_TREE_ROW_HEIGHT, MAX_TREE_ROW_HEIGHT
            ),
            default_left_view=left_view,
            auto_expand_structure=bool(data.get("auto_expand_structure", defaults.auto_expand_structure)),
        )


def load_preferences(path: Path = DEFAULT_SETTINGS_PATH) -> AppPreferences:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return AppPreferences()
    if not isinstance(data, dict):
        return AppPreferences()
    return AppPreferences.from_dict(data)


def save_preferences(prefs: AppPreferences, path: Path = DEFAULT_SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(prefs.to_dict(), f, indent=2)
    os.replace(tmp_path, path)


def load_theme_name(path: Path = DEFAULT_SETTINGS_PATH) -> str:
    return load_preferences(path).theme


def save_theme_name(name: str, path: Path = DEFAULT_SETTINGS_PATH) -> None:
    prefs = load_preferences(path)
    prefs.theme = name
    save_preferences(prefs, path)
