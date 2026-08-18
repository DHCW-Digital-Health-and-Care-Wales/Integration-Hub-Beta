from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from defusedxml import ElementTree as ET


def _resolve_base_dir(structure_xsd_path: Optional[str]) -> str:
    if structure_xsd_path:
        return os.path.dirname(structure_xsd_path)
    raise ValueError(
        "structure_xsd_path is required to resolve base HL7 XSDs; no default flow will be used"
    )


@lru_cache(maxsize=32)
def _detect_base_prefix(structure_xsd_path: Optional[str]) -> Optional[str]:
    """
    Detect the '<prefix>' used by a modular flow schema that includes shared
    '<prefix>_fields.xsd' / '<prefix>_segments.xsd' / '<prefix>_types.xsd' files.

    Not every schema follows this modular convention — some structure schemas (e.g.
    RISP's ORU_R01/OMG_O19) are fully self-contained, single-file XSDs with segment
    and component types declared inline rather than via includes. For those, this
    returns ``None`` so callers can fall back to parsing the structure XSD directly
    instead of failing.
    """
    if not structure_xsd_path:
        raise ValueError("structure_xsd_path is required to detect base XSD prefix")
    tree = ET.parse(structure_xsd_path)
    root = tree.getroot()
    xs = "{http://www.w3.org/2001/XMLSchema}"
    for inc in root.findall(f"{xs}include"):
        loc = inc.get("schemaLocation")
        if not loc:
            continue
        filename = os.path.basename(loc)
        if filename.endswith("_segments.xsd"):
            return filename[: -len("_segments.xsd")]
    return None


@lru_cache(maxsize=64)
def _load_message_structure(
    structure_xsd_path: str,
    structure_id: str,
) -> Tuple[List[Tuple[str, int | str, int | str]] | None, Dict[str, List[str]]]:
    tree = ET.parse(structure_xsd_path)
    root = tree.getroot()
    xs = "{http://www.w3.org/2001/XMLSchema}"

    complex_sequences: Dict[str, List[Tuple[str, int | str, int | str]]] = {}
    for ctype in root.findall(f"{xs}complexType"):
        type_name = ctype.get("name")
        if not type_name:
            continue
        seq = ctype.find(f"{xs}sequence")
        if seq is None:
            continue
        items: List[Tuple[str, int | str, int | str]] = []
        for el in seq.findall(f"{xs}element"):
            ref = el.get("ref")
            if not ref:
                continue
            min_occurs_attr = el.get("minOccurs")
            max_occurs_attr = el.get("maxOccurs")
            min_occurs: int | str = int(min_occurs_attr) if min_occurs_attr else 1
            if max_occurs_attr is None:
                max_occurs: int | str = 1
            elif max_occurs_attr == "unbounded":
                max_occurs = "unbounded"
            else:
                try:
                    max_occurs = int(max_occurs_attr)
                except Exception:
                    max_occurs = 1
            items.append((ref, min_occurs, max_occurs))
        if items:
            complex_sequences[type_name] = items

    desired_type = f"{structure_id}.CONTENT"
    root_sequence: List[Tuple[str, int | str, int | str]] | None = complex_sequences.get(desired_type)

    group_children_map: Dict[str, List[str]] = {}
    for type_name, items in complex_sequences.items():
        if not type_name.endswith(".CONTENT"):
            continue
        element_name = type_name[: -len(".CONTENT")]
        if "." in element_name:
            child_names = [ref for ref, _min_o, _max_o in items]
            group_children_map[element_name] = child_names

    if root_sequence is not None:
        return root_sequence, group_children_map

    # Fall back for self-contained schemas (e.g. RISP's ORU_R01/OMG_O19) that declare
    # message groups as anonymous complexTypes nested directly under <xsd:element>
    # tags, rather than as named top-level "<Structure>.CONTENT" types.
    return _load_inline_message_structure(root, structure_id, xs)


def _parse_occurs(element: Any) -> Tuple[int | str, int | str]:
    min_occurs_attr = element.get("minOccurs")
    max_occurs_attr = element.get("maxOccurs")
    min_occurs: int | str = int(min_occurs_attr) if min_occurs_attr else 1
    if max_occurs_attr is None:
        max_occurs: int | str = 1
    elif max_occurs_attr == "unbounded":
        max_occurs = "unbounded"
    else:
        try:
            max_occurs = int(max_occurs_attr)
        except ValueError:
            max_occurs = 1
    return min_occurs, max_occurs


def _load_inline_message_structure(
    root: Any,
    structure_id: str,
    xs: str,
) -> Tuple[List[Tuple[str, int | str, int | str]] | None, Dict[str, List[str]]]:
    """
    Derive the root segment/group order and group nesting for a self-contained schema
    by walking the root ``<xsd:element name="{structure_id}">`` recursively.

    In this style, group elements (e.g. ``ORU_R01.PATIENT_RESULT``) have an inline,
    anonymous ``complexType`` rather than a ``type=`` attribute referencing a shared
    named type; leaf/segment elements (e.g. ``PID``, ``PV1``) reference a named
    segment type via ``type=`` and have no nested sequence of their own.
    """
    root_element = next(
        (el for el in root.findall(f"{xs}element") if el.get("name") == structure_id),
        None,
    )
    if root_element is None:
        return None, {}

    group_children_map: Dict[str, List[str]] = {}

    def walk(element: Any) -> List[Tuple[str, int | str, int | str]]:
        ctype = element.find(f"{xs}complexType")
        if ctype is None:
            return []
        seq = ctype.find(f"{xs}sequence")
        if seq is None:
            return []

        items: List[Tuple[str, int | str, int | str]] = []
        for child_el in seq.findall(f"{xs}element"):
            name = child_el.get("name")
            if not name:
                continue
            min_occurs, max_occurs = _parse_occurs(child_el)
            items.append((name, min_occurs, max_occurs))

            if child_el.get("type") is None:
                nested_items = walk(child_el)
                if nested_items:
                    group_children_map[name] = [ref for ref, _min_o, _max_o in nested_items]
        return items

    root_sequence = walk(root_element)
    return (root_sequence or None), group_children_map


