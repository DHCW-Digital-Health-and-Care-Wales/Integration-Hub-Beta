"""Small, namespace-agnostic XML helpers shared by content adapters."""
from __future__ import annotations

from typing import List

# Only used to inspect trusted, already-parsed elements; untrusted input must
# always be parsed via defusedxml before reaching these helpers.
from xml.etree.ElementTree import Element as XmlElement  # nosec B405


def local_name(tag: str) -> str:
    """Strip a namespace prefix (``{uri}Name``) from an element tag, if present."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def find_first_text(parent: XmlElement, path_segments: List[str]) -> str | None:
    """Walk a path of local element names from ``parent`` and return the first non-blank text.

    Namespace prefixes are ignored, so the same path works regardless of which XML namespace a
    sender uses (mirrors the matching behaviour already used for HL7 v2.xml assigning-authority
    lookups in the SOAP server).
    """
    current_nodes: List[XmlElement] = [parent]

    for segment in path_segments:
        next_nodes: List[XmlElement] = []
        for node in current_nodes:
            for child in list(node):
                if isinstance(child.tag, str) and local_name(child.tag) == segment:
                    next_nodes.append(child)
        if not next_nodes:
            return None
        current_nodes = next_nodes

    for node in current_nodes:
        if node.text and node.text.strip():
            return node.text.strip()

    return None
