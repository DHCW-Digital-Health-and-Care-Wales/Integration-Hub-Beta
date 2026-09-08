"""HL7 v2 ER7 escape sequence <-> literal character conversion.

ER7 field values may contain HL7's backslash-delimited escape sequences (e.g. ``\\T\\`` for a
literal ``&``) so that a literal occurrence of a delimiter character doesn't get misread as a real
field/component/repetition/escape separator. XML has no such concept - a literal ``&`` is instead
represented via the XML entity ``&amp;`` (handled automatically by the XML serializer/parser).

So the two conversion directions need opposite treatment:

- ``er7_to_xml`` (see ``converter.py``): decode ER7 escape sequences to literal characters
  *before* assigning them as XML element text - the XML serializer then entity-encodes any
  resulting ``&``/``<``/``>`` automatically.
- ``xml_to_er7``: after the XML parser has already decoded entities back to literal characters,
  re-encode any literal HL7 delimiter characters back into escape sequences before assembling the
  pipe-and-hat ER7 string, so they aren't misread as real delimiters.

Only the escape sequences below are supported (mnemonic separators + CR/LF). Any other/unknown
``\\Xxx\\`` sequence is left untouched by ``decode_hl7_escapes`` rather than risk corrupting data.
"""

from __future__ import annotations

import re
from typing import Match

# Simple mnemonic escapes: \F\ \S\ \R\ \T\ \E\ and the non-standard-but-common \.br\ line break.
# \.br\ is decode-only (see module docstring) - it's never produced by encode_hl7_escapes.
_SIMPLE_ESCAPES = {
    "F": "|",
    "S": "^",
    "R": "~",
    "T": "&",
    "E": "\\",
    ".br": "\r\n",
}

# Matches any backslash-delimited escape sequence, e.g. \T\, \X0D\, \.br\.
_ESCAPE_PATTERN = re.compile(r"\\([^\\]*)\\")

_HEX_DIGITS = set("0123456789ABCDEFabcdef")


def _decode_one(match: "Match[str]") -> str:
    code = match.group(1)
    if code in _SIMPLE_ESCAPES:
        return _SIMPLE_ESCAPES[code]

    if code.startswith("X") and len(code) > 1:
        hex_digits = code[1:]
        if len(hex_digits) % 2 == 0 and all(c in _HEX_DIGITS for c in hex_digits):
            try:
                return bytes.fromhex(hex_digits).decode("utf-8", errors="replace")
            except ValueError:
                pass

    # Unknown/unsupported escape sequence - leave it untouched rather than corrupt data.
    return match.group(0)


def decode_hl7_escapes(text: str) -> str:
    """Decode HL7 ER7 escape sequences (``\\T\\``, ``\\X0D\\``, etc.) into literal characters.

    Use this before assigning ER7-sourced text as XML element text (``er7_to_xml``) - the XML
    serializer will then entity-encode any resulting ``&``/``<``/``>`` as needed.
    """
    if not text or "\\" not in text:
        return text
    return _ESCAPE_PATTERN.sub(_decode_one, text)


def encode_hl7_escapes(text: str) -> str:
    """Encode literal HL7 delimiter characters (and CR/LF) back into ER7 escape sequences.

    Use this on text already extracted from XML (entities already decoded to literal characters by
    the XML parser) before assembling it into a pipe-and-hat ER7 field, so literal delimiter
    characters in the data aren't misread as real field/component/repetition separators.

    The backslash character must be escaped first - otherwise the backslashes introduced by
    escaping the other characters would themselves be mistaken for delimiters.
    """
    if not text:
        return text
    text = text.replace("\\", "\\E\\")
    text = text.replace("|", "\\F\\")
    text = text.replace("^", "\\S\\")
    text = text.replace("~", "\\R\\")
    text = text.replace("&", "\\T\\")
    text = text.replace("\r\n", "\\X0D\\\\X0A\\")
    text = text.replace("\r", "\\X0D\\")
    text = text.replace("\n", "\\X0A\\")
    return text
