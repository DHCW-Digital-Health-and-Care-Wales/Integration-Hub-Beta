import unittest

from ultra7.ui.themes import DEFAULT_THEME_NAME, THEMES, get_theme


class TestThemes(unittest.TestCase):
    def test_has_ten_themes(self) -> None:
        self.assertEqual(len(THEMES), 10)

    def test_names_are_unique(self) -> None:
        names = [theme.name for theme in THEMES]
        self.assertEqual(len(names), len(set(names)))

    def test_default_theme_is_first(self) -> None:
        self.assertEqual(DEFAULT_THEME_NAME, THEMES[0].name)

    def test_get_theme_known_name(self) -> None:
        theme = get_theme("Dracula")
        self.assertEqual(theme.name, "Dracula")

    def test_get_theme_unknown_name_falls_back_to_default(self) -> None:
        theme = get_theme("Not A Real Theme")
        self.assertEqual(theme.name, DEFAULT_THEME_NAME)

    def test_all_colours_are_hex_strings(self) -> None:
        for theme in THEMES:
            for value in (theme.bg, theme.fg, theme.pane_bg, theme.pane_fg, theme.accent,
                          theme.select_bg, theme.select_fg, theme.syntax_keyword, theme.syntax_punct,
                          theme.syntax_string, theme.syntax_accent):
                self.assertTrue(value.startswith("#") and len(value) == 7, value)

    def test_syntax_colours_are_distinct_from_pane_background(self) -> None:
        for theme in THEMES:
            for value in (theme.syntax_keyword, theme.syntax_punct, theme.syntax_string, theme.syntax_accent):
                self.assertNotEqual(value, theme.pane_bg, f"{theme.name}: syntax colour matches pane_bg")


if __name__ == "__main__":
    unittest.main()
