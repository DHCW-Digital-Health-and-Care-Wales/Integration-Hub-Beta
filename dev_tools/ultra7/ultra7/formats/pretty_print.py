"""Pretty-print (reformat) XML and JSON message content for easier editing."""
from __future__ import annotations

import json
from xml.dom import minidom

from ultra7.models import MessageFormat

SUPPORTED_FORMATS: tuple[MessageFormat, ...] = ("xml", "json")


def pretty_print(content: str, message_format: MessageFormat) -> str:
    """Return a reformatted, indented version of `content`.

    Raises ValueError if the format isn't supported or the content doesn't parse.
    """
    if message_format == "json":
        return _pretty_json(content)
    if message_format == "xml":
        return _pretty_xml(content)
    raise ValueError(f"Formatting is not supported for '{message_format}' messages")


def _pretty_json(content: str) -> str:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    return json.dumps(parsed, indent=2)


def _pretty_xml(content: str) -> str:
    try:
        dom = minidom.parseString(content)
    except Exception as exc:  # noqa: BLE001 — minidom raises various ExpatError subclasses
        raise ValueError(f"Invalid XML: {exc}") from exc
    pretty = dom.toprettyxml(indent="  ")
    # minidom.toprettyxml leaves blank lines around text-only elements; drop them.
    lines = [line for line in pretty.splitlines() if line.strip()]
    return "\n".join(lines)
