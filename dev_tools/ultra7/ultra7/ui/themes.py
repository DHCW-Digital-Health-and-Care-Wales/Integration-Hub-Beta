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
    border: str = ""
    """Colour for borders and separator lines between panels. Defaults to a subtle accent of bg if empty."""


THEMES: tuple[Theme, ...] = (
    Theme("DHCW Light", bg="#F4F7FB", fg="#1B294A", pane_bg="#FFFFFF", pane_fg="#1B294A",
          accent="#325083", select_bg="#12A3C9", select_fg="#FFFFFF",
          syntax_keyword="#1B294A", syntax_punct="#12A3C9", syntax_string="#325083", syntax_accent="#B8860B",
          border="#D4DCE8"),
    Theme("DHCW Dark", bg="#131D35", fg="#E6EDF7", pane_bg="#1B294A", pane_fg="#F1F5FB",
          accent="#12A3C9", select_bg="#325083", select_fg="#FFFFFF",
          syntax_keyword="#5CD1F0", syntax_punct="#9FB3D1", syntax_string="#F8CA4D", syntax_accent="#7EE787",
          border="#2B3E6B"),
    Theme("GitHub Light", bg="#F6F8FA", fg="#1F2328", pane_bg="#FFFFFF", pane_fg="#1F2328",
          accent="#0969DA", select_bg="#0969DA", select_fg="#FFFFFF",
          syntax_keyword="#CF222E", syntax_punct="#57606A", syntax_string="#0A3069", syntax_accent="#0550AE",
          border="#D0D7DE"),
    Theme("Catppuccin Latte", bg="#EFF1F5", fg="#4C4F69", pane_bg="#FFFFFF", pane_fg="#4C4F69",
          accent="#1E66F5", select_bg="#1E66F5", select_fg="#FFFFFF",
          syntax_keyword="#8839EF", syntax_punct="#6C6F85", syntax_string="#40A02B", syntax_accent="#DF8E1D",
          border="#CCD0DA"),
    Theme("Catppuccin Mocha", bg="#1E1E2E", fg="#CDD6F4", pane_bg="#181825", pane_fg="#CDD6F4",
          accent="#89B4FA", select_bg="#45475A", select_fg="#CDD6F4",
          syntax_keyword="#CBA6F7", syntax_punct="#9399B2", syntax_string="#A6E3A1", syntax_accent="#F9E2AF",
          border="#313244"),
    Theme("Tokyo Night", bg="#1A1B26", fg="#C0CAF5", pane_bg="#16161E", pane_fg="#C0CAF5",
          accent="#7AA2F7", select_bg="#33467C", select_fg="#FFFFFF",
          syntax_keyword="#BB9AF7", syntax_punct="#89DDFF", syntax_string="#9ECE6A", syntax_accent="#E0AF68",
          border="#292E42"),
    Theme("Dark", bg="#1E1E1E", fg="#D4D4D4", pane_bg="#252526", pane_fg="#D4D4D4",
          accent="#569CD6", select_bg="#264F78", select_fg="#FFFFFF",
          syntax_keyword="#569CD6", syntax_punct="#D4D4D4", syntax_string="#CE9178", syntax_accent="#DCDCAA",
          border="#3C3C3C"),
    Theme("One Dark", bg="#282C34", fg="#ABB2BF", pane_bg="#21252B", pane_fg="#ABB2BF",
          accent="#61AFEF", select_bg="#3E4451", select_fg="#FFFFFF",
          syntax_keyword="#C678DD", syntax_punct="#ABB2BF", syntax_string="#98C379", syntax_accent="#E5C07B",
          border="#3E4451"),
    Theme("Dracula", bg="#282A36", fg="#F8F8F2", pane_bg="#21222C", pane_fg="#F8F8F2",
          accent="#BD93F9", select_bg="#44475A", select_fg="#F8F8F2",
          syntax_keyword="#FF79C6", syntax_punct="#F8F8F2", syntax_string="#F1FA8C", syntax_accent="#8BE9FD",
          border="#44475A"),
    Theme("Nord", bg="#2E3440", fg="#D8DEE9", pane_bg="#3B4252", pane_fg="#E5E9F0",
          accent="#88C0D0", select_bg="#4C566A", select_fg="#ECEFF4",
          syntax_keyword="#81A1C1", syntax_punct="#D8DEE9", syntax_string="#A3BE8C", syntax_accent="#EBCB8B",
          border="#434C5E"),
    Theme("Solarized Light", bg="#FDF6E3", fg="#657B83", pane_bg="#EEE8D5", pane_fg="#586E75",
          accent="#268BD2", select_bg="#268BD2", select_fg="#FDF6E3",
          syntax_keyword="#268BD2", syntax_punct="#586E75", syntax_string="#2AA198", syntax_accent="#B58900",
          border="#DDD6C1"),
    Theme("Solarized Dark", bg="#002B36", fg="#839496", pane_bg="#073642", pane_fg="#93A1A1",
          accent="#268BD2", select_bg="#268BD2", select_fg="#002B36",
          syntax_keyword="#268BD2", syntax_punct="#93A1A1", syntax_string="#2AA198", syntax_accent="#B58900",
          border="#094E5C"),
    Theme("Monokai", bg="#272822", fg="#F8F8F2", pane_bg="#1E1F1C", pane_fg="#F8F8F2",
          accent="#A6E22E", select_bg="#49483E", select_fg="#F8F8F2",
          syntax_keyword="#F92672", syntax_punct="#F8F8F2", syntax_string="#E6DB74", syntax_accent="#66D9EF",
          border="#3E3D32"),
    Theme("Gruvbox Dark", bg="#282828", fg="#EBDBB2", pane_bg="#32302F", pane_fg="#EBDBB2",
          accent="#FE8019", select_bg="#504945", select_fg="#FBF1C7",
          syntax_keyword="#83A598", syntax_punct="#EBDBB2", syntax_string="#B8BB26", syntax_accent="#FABD2F",
          border="#3C3836"),
    Theme("High Contrast", bg="#000000", fg="#FFFFFF", pane_bg="#000000", pane_fg="#FFFFFF",
          accent="#FFFF00", select_bg="#FFFF00", select_fg="#000000",
          syntax_keyword="#00FFFF", syntax_punct="#FFFFFF", syntax_string="#00FF00", syntax_accent="#FFFF00",
          border="#666666"),
)

THEMES_BY_NAME: dict[str, Theme] = {theme.name: theme for theme in THEMES}
DEFAULT_THEME_NAME = THEMES[0].name


def get_theme(name: str) -> Theme:
    return THEMES_BY_NAME.get(name, THEMES_BY_NAME[DEFAULT_THEME_NAME])


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def blend_colors(hex_a: str, hex_b: str, weight_b: float) -> str:
    """Linearly interpolate between two #RRGGBB hex colours."""
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    w = max(0.0, min(1.0, weight_b))
    return _rgb_to_hex(
        round(ra * (1 - w) + rb * w),
        round(ga * (1 - w) + gb * w),
        round(ba * (1 - w) + bb * w),
    )


def is_dark_theme(theme: Theme) -> bool:
    """Return True if the theme's window background is perceptually dark."""
    r, g, b = _hex_to_rgb(theme.bg)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return luminance < 0.5


def get_border_color(theme: Theme) -> str:
    """Return the theme's border colour, falling back to a subtle divider derived from bg."""
    if theme.border:
        return theme.border
    r, g, b = _hex_to_rgb(theme.bg)
    factor = 0.82
    return _rgb_to_hex(int(r * factor), int(g * factor), int(b * factor))


def get_muted_fg(theme: Theme) -> str:
    """Subtle secondary foreground colour for section labels and hints."""
    return blend_colors(theme.fg, theme.bg, 0.42)


def get_hover_bg(theme: Theme) -> str:
    """Subtle hover surface colour for buttons and list rows."""
    return blend_colors(theme.pane_bg, theme.accent, 0.14 if is_dark_theme(theme) else 0.10)


def get_semantic_colors(theme: Theme) -> dict[str, str]:
    """Return theme-appropriate colours for ok/error/info/warning/iterate badges."""
    if is_dark_theme(theme):
        return {
            "ok": "#4ADE80",
            "error": "#F87171",
            "info": "#94A3B8",
            "danger": "#EF4444",
            "iterate_bg": "#F8CA4D",
            "iterate_fg": "#1B294A",
        }
    return {
        "ok": "#15803D",
        "error": "#DC2626",
        "info": "#64748B",
        "danger": "#DC2626",
        "iterate_bg": "#F8CA4D",
        "iterate_fg": "#1B294A",
    }
