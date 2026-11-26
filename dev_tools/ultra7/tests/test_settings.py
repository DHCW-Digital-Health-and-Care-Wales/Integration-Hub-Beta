import gc
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from ultra7.settings import (
    AppPreferences,
    load_preferences,
    load_theme_name,
    save_preferences,
    save_theme_name,
)
from ultra7.ui.preferences_dialog import PreferencesDialog
from ultra7.ui.themes import DEFAULT_THEME_NAME


def _tk_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


class TestSettings(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "settings.json"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_missing_file_returns_default(self) -> None:
        self.assertEqual(load_theme_name(self.path), DEFAULT_THEME_NAME)
        prefs = load_preferences(self.path)
        self.assertEqual(prefs, AppPreferences())

    def test_save_and_load_round_trip(self) -> None:
        save_theme_name("Dracula", self.path)
        self.assertEqual(load_theme_name(self.path), "Dracula")

    def test_preferences_round_trip_and_theme_save_preserves_fonts(self) -> None:
        prefs = AppPreferences(
            theme="Tokyo Night",
            ui_font_family="Helvetica Neue",
            ui_font_size=12,
            editor_font_family="Monaco",
            editor_font_size=14,
            log_font_size=11,
            editor_word_wrap=True,
            tree_row_height=28,
            default_left_view="structure",
            auto_expand_structure=True,
        )
        save_preferences(prefs, self.path)
        loaded = load_preferences(self.path)
        self.assertEqual(loaded, prefs)

        # Updating only the theme preserves all font & editor preferences.
        save_theme_name("DHCW Dark", self.path)
        after_theme = load_preferences(self.path)
        self.assertEqual(after_theme.theme, "DHCW Dark")
        self.assertEqual(after_theme.editor_font_family, "Monaco")
        self.assertEqual(after_theme.editor_font_size, 14)
        self.assertTrue(after_theme.editor_word_wrap)

    def test_out_of_range_values_are_clamped(self) -> None:
        prefs = AppPreferences.from_dict(
            {"ui_font_size": 999, "editor_font_size": 2, "log_font_size": "bad", "tree_row_height": 100}
        )
        self.assertEqual(prefs.ui_font_size, 20)
        self.assertEqual(prefs.editor_font_size, 8)
        self.assertEqual(prefs.log_font_size, 10)
        self.assertEqual(prefs.tree_row_height, 40)

    def test_corrupt_file_falls_back_to_default(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("not valid json", encoding="utf-8")
        self.assertEqual(load_theme_name(self.path), DEFAULT_THEME_NAME)
        self.assertEqual(load_preferences(self.path), AppPreferences())


@unittest.skipUnless(_tk_available(), "requires a Tk display")
class TestPreferencesDialog(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()
        gc.collect()

    def test_dialog_builds_and_resets_preferences(self) -> None:
        initial = AppPreferences(theme="Catppuccin Mocha", editor_font_size=15, editor_word_wrap=True)
        dlg = PreferencesDialog(self.root, initial)
        built = dlg.build_preferences()
        self.assertEqual(built.theme, "Catppuccin Mocha")
        self.assertEqual(built.editor_font_size, 15)
        self.assertTrue(built.editor_word_wrap)

        dlg._reset_defaults()
        reset = dlg.build_preferences()
        self.assertEqual(reset, AppPreferences())
        dlg.destroy()


if __name__ == "__main__":
    unittest.main()
