"""Export message content to disk as .hl7 / .xml / .json files."""
from __future__ import annotations

import re

from ultra7.models import MessageFormat

EXTENSION_BY_FORMAT: dict[MessageFormat, str] = {"hl7": ".hl7", "xml": ".xml", "json": ".json"}

_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9 _-]")


def extension_for(message_format: MessageFormat) -> str:
    return EXTENSION_BY_FORMAT.get(message_format, ".txt")


def sanitize_filename(name: str) -> str:
    """Sanitize a message name into a safe filename stem (no path separators)."""
    safe = _INVALID_NAME_CHARS.sub("_", name).strip()
    return safe or "message"


def unique_filename(stem: str, ext: str, used: set[str]) -> str:
    """Return `stem + ext`, disambiguated with ' (2)', ' (3)', ... if already used."""
    candidate = f"{stem}{ext}"
    counter = 2
    while candidate in used:
        candidate = f"{stem} ({counter}){ext}"
        counter += 1
    used.add(candidate)
    return candidate
