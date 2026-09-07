import tempfile
import unittest
from pathlib import Path

from ultra7.settings import load_theme_name, save_theme_name
from ultra7.ui.themes import DEFAULT_THEME_NAME


class TestSettings(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "settings.json"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_missing_file_returns_default(self) -> None:
        self.assertEqual(load_theme_name(self.path), DEFAULT_THEME_NAME)

    def test_save_and_load_round_trip(self) -> None:
        save_theme_name("Dracula", self.path)
        self.assertEqual(load_theme_name(self.path), "Dracula")

    def test_corrupt_file_falls_back_to_default(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("not valid json", encoding="utf-8")
        self.assertEqual(load_theme_name(self.path), DEFAULT_THEME_NAME)


if __name__ == "__main__":
    unittest.main()
