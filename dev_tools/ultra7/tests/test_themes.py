import unittest

from ultra7.ui.themes import DEFAULT_THEME_NAME, THEMES, _contrast_ratio, get_accent_fg, get_theme


class TestThemes(unittest.TestCase):
    def test_has_fifteen_themes(self) -> None:
        self.assertEqual(len(THEMES), 15)

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

    def test_accent_foreground_meets_wcag_aa_contrast(self) -> None:
        for theme in THEMES:
            fg = get_accent_fg(theme)
            ratio = _contrast_ratio(theme.accent, fg)
            self.assertGreaterEqual(
                ratio, 4.5, f"{theme.name}: contrast {ratio:.2f} too low for {fg} on {theme.accent}"
            )


if __name__ == "__main__":
    unittest.main()
