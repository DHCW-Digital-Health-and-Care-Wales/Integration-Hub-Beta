"""Colour theme definitions for Ultra7."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """A full colour palette applied across the app's widgets."""

    name: str
    bg: str
    """Window / frame background."""
    fg: str
    """Primary text colour."""
    pane_bg: str
    """Background for text/listbox panes (editor, sidebar, log)."""
    pane_fg: str
    """Foreground for text/listbox panes."""
    accent: str
    """Accent colour used for headings and button hover states."""
    select_bg: str
    """Selection background in text/listbox panes."""
    select_fg: str
    """Selection foreground in text/listbox panes."""
    syntax_keyword: str
    """Syntax highlight colour for structural tokens (HL7 segments, XML tags, JSON keys)."""
    syntax_punct: str
    """Syntax highlight colour for delimiters/attributes/plain punctuation."""
    syntax_string: str
    """Syntax highlight colour for string/text values."""
    syntax_accent: str
    """Syntax highlight colour for numbers/literals/brackets."""


THEMES: tuple[Theme, ...] = (
    Theme("DHCW Light", bg="#F5F7FA", fg="#1B294A", pane_bg="#FFFFFF", pane_fg="#1B294A",
          accent="#325083", select_bg="#12A3C9", select_fg="#FFFFFF",
          syntax_keyword="#1B294A", syntax_punct="#12A3C9", syntax_string="#325083", syntax_accent="#B8860B"),
    Theme("Dark", bg="#1E1E1E", fg="#D4D4D4", pane_bg="#252526", pane_fg="#D4D4D4",
          accent="#569CD6", select_bg="#264F78", select_fg="#FFFFFF",
          syntax_keyword="#569CD6", syntax_punct="#D4D4D4", syntax_string="#CE9178", syntax_accent="#DCDCAA"),
    Theme("Solarized Light", bg="#FDF6E3", fg="#657B83", pane_bg="#EEE8D5", pane_fg="#586E75",
          accent="#268BD2", select_bg="#268BD2", select_fg="#FDF6E3",
          syntax_keyword="#268BD2", syntax_punct="#586E75", syntax_string="#2AA198", syntax_accent="#B58900"),
    Theme("Solarized Dark", bg="#002B36", fg="#839496", pane_bg="#073642", pane_fg="#93A1A1",
          accent="#268BD2", select_bg="#268BD2", select_fg="#002B36",
          syntax_keyword="#268BD2", syntax_punct="#93A1A1", syntax_string="#2AA198", syntax_accent="#B58900"),
    Theme("Dracula", bg="#282A36", fg="#F8F8F2", pane_bg="#21222C", pane_fg="#F8F8F2",
          accent="#BD93F9", select_bg="#44475A", select_fg="#F8F8F2",
          syntax_keyword="#FF79C6", syntax_punct="#F8F8F2", syntax_string="#F1FA8C", syntax_accent="#8BE9FD"),
    Theme("Monokai", bg="#272822", fg="#F8F8F2", pane_bg="#1E1F1C", pane_fg="#F8F8F2",
          accent="#A6E22E", select_bg="#49483E", select_fg="#F8F8F2",
          syntax_keyword="#F92672", syntax_punct="#F8F8F2", syntax_string="#E6DB74", syntax_accent="#66D9EF"),
    Theme("Nord", bg="#2E3440", fg="#D8DEE9", pane_bg="#3B4252", pane_fg="#E5E9F0",
          accent="#88C0D0", select_bg="#4C566A", select_fg="#ECEFF4",
          syntax_keyword="#81A1C1", syntax_punct="#D8DEE9", syntax_string="#A3BE8C", syntax_accent="#EBCB8B"),
    Theme("Gruvbox Dark", bg="#282828", fg="#EBDBB2", pane_bg="#32302F", pane_fg="#EBDBB2",
          accent="#FE8019", select_bg="#504945", select_fg="#FBF1C7",
          syntax_keyword="#83A598", syntax_punct="#EBDBB2", syntax_string="#B8BB26", syntax_accent="#FABD2F"),
    Theme("One Dark", bg="#282C34", fg="#ABB2BF", pane_bg="#21252B", pane_fg="#ABB2BF",
          accent="#61AFEF", select_bg="#3E4451", select_fg="#FFFFFF",
          syntax_keyword="#C678DD", syntax_punct="#ABB2BF", syntax_string="#98C379", syntax_accent="#E5C07B"),
    Theme("High Contrast", bg="#000000", fg="#FFFFFF", pane_bg="#000000", pane_fg="#FFFFFF",
          accent="#FFFF00", select_bg="#FFFF00", select_fg="#000000",
          syntax_keyword="#00FFFF", syntax_punct="#FFFFFF", syntax_string="#00FF00", syntax_accent="#FFFF00"),
)

THEMES_BY_NAME: dict[str, Theme] = {theme.name: theme for theme in THEMES}
DEFAULT_THEME_NAME = THEMES[0].name


def get_theme(name: str) -> Theme:
    return THEMES_BY_NAME.get(name, THEMES_BY_NAME[DEFAULT_THEME_NAME])
