"""Regex-based syntax highlighting for a tkinter Text widget.

Kept deliberately lightweight (no external editor-widget dependency) — each
format defines a list of (tag, regex, role) rules that are re-applied to the
whole buffer on edit. Fine for the message sizes this tool deals with (single
HL7/XML/JSON messages, not large files). Tag *colours* are theme-driven (see
`configure_tags`) so they stay legible across light and dark themes.
"""
from __future__ import annotations

import re
import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ultra7.models import MessageFormat

if TYPE_CHECKING:
    from ultra7.ui.themes import Theme


@dataclass
class HighlightRule:
    tag: str
    pattern: re.Pattern[str]
    role: str
    """Which theme colour to use: 'keyword', 'punct', 'string', or 'accent'."""


_HL7_RULES = [
    HighlightRule("hl7-segment", re.compile(r"^[A-Z][A-Z0-9][A-Z0-9](?=\|)", re.MULTILINE), "keyword"),
    HighlightRule("hl7-delimiter", re.compile(r"[|^~\\&]"), "punct"),
]

_XML_RULES = [
    HighlightRule("xml-tag", re.compile(r"</?[A-Za-z_][\w:.-]*"), "keyword"),
    HighlightRule("xml-attr", re.compile(r'\b[A-Za-z_][\w:.-]*(?==")'), "punct"),
    HighlightRule("xml-string", re.compile(r'"[^"]*"'), "string"),
    HighlightRule("xml-bracket", re.compile(r"[<>/]"), "accent"),
]

_JSON_RULES = [
    HighlightRule("json-key", re.compile(r'"[^"]*"(?=\s*:)'), "keyword"),
    HighlightRule("json-string", re.compile(r'(?<=:)\s*"[^"]*"'), "string"),
    HighlightRule("json-number", re.compile(r"(?<!\w)-?\d+(\.\d+)?\b"), "punct"),
    HighlightRule("json-literal", re.compile(r"\b(true|false|null)\b"), "accent"),
]

_RULES_BY_FORMAT: dict[MessageFormat, list[HighlightRule]] = {
    "hl7": _HL7_RULES,
    "xml": _XML_RULES,
    "json": _JSON_RULES,
}


def configure_tags(text_widget: tk.Text, theme: Theme) -> None:
    """(Re)configure the tk text tag colours for the given theme. Safe to call again on theme change."""
    role_colors = {
        "keyword": theme.syntax_keyword,
        "punct": theme.syntax_punct,
        "string": theme.syntax_string,
        "accent": theme.syntax_accent,
    }
    for rules in _RULES_BY_FORMAT.values():
        for rule in rules:
            text_widget.tag_configure(rule.tag, foreground=role_colors[rule.role])


def highlight(text_widget: tk.Text, message_format: MessageFormat) -> None:
    """Re-apply syntax highlighting for *message_format* over the whole buffer."""
    rules = _RULES_BY_FORMAT.get(message_format, [])
    all_tags = [rule.tag for fmt_rules in _RULES_BY_FORMAT.values() for rule in fmt_rules]
    for tag in all_tags:
        text_widget.tag_remove(tag, "1.0", tk.END)

    content = text_widget.get("1.0", tk.END)
    for rule in rules:
        for match in rule.pattern.finditer(content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            text_widget.tag_add(rule.tag, start, end)
