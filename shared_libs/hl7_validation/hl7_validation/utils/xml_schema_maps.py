from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Tuple

from defusedxml import ElementTree as ET

XS_NS = "{http://www.w3.org/2001/XMLSchema}"


@lru_cache(maxsize=8)
def _load_hl7_type_maps(base_dir: str, base_prefix: str) -> Tuple[Dict[str, str], Dict[str, List[str]], Dict[str, str]]:
    fields_path = os.path.join(base_dir, f"{base_prefix}_fields.xsd")
    types_path = os.path.join(base_dir, f"{base_prefix}_types.xsd")

    fields_tree = ET.parse(fields_path)
    types_tree = ET.parse(types_path)

    fields_root = fields_tree.getroot()
    types_root = types_tree.getroot()

    element_to_type: Dict[str, str] = {}
    for el in fields_root.findall(f"{XS_NS}element"):
        name = el.get("name")
        type_name = el.get("type")
        if name and type_name:
            element_to_type[name] = type_name
    for el in types_root.findall(f"{XS_NS}element"):
        name = el.get("name")
        type_name = el.get("type")
        if name and type_name:
            element_to_type[name] = type_name

    type_children: Dict[str, List[str]] = {}
    type_base: Dict[str, str] = {}
    for ctype in types_root.findall(f"{XS_NS}complexType"):
        type_name = ctype.get("name")
        if not type_name:
            continue
        seq = ctype.find(f"{XS_NS}sequence")
        if seq is not None:
            child_names: List[str] = []
            for child_el in seq.findall(f"{XS_NS}element"):
                ref = child_el.get("ref")
                if ref:
                    child_names.append(ref)
            if child_names:
                type_children[type_name] = child_names
        cc = ctype.find(f"{XS_NS}complexContent")
        if cc is not None:
            ext = cc.find(f"{XS_NS}extension")
            if ext is not None and ext.get("base"):
                type_base[type_name] = ext.get("base")  # type: ignore[arg-type]

    return element_to_type, type_children, type_base


@lru_cache(maxsize=8)
def _load_segments_info(
    base_dir: str, base_prefix: str
) -> Tuple[Dict[str, int | str], Dict[str, List[Tuple[str, int | str, int | str]]]]:
    segments_path = os.path.join(base_dir, f"{base_prefix}_segments.xsd")
    root = ET.parse(segments_path).getroot()

    occurs: Dict[str, int | str] = {}
    sequences: Dict[str, List[Tuple[str, int | str, int | str]]] = {}

    for ctype in root.findall(f"{XS_NS}complexType"):
        type_name = ctype.get("name")
        seq = ctype.find(f"{XS_NS}sequence")
        if seq is None:
            continue

        # Build occurs map over all elements
        for el in seq.findall(f"{XS_NS}element"):
            ref = el.get("ref")
            if not ref:
                continue
            max_occurs_attr = el.get("maxOccurs")
            if max_occurs_attr is None:
                occurs[ref] = 1
            elif max_occurs_attr == "unbounded":
                occurs[ref] = "unbounded"
            else:
                try:
                    occurs[ref] = int(max_occurs_attr)
                except Exception:
                    occurs[ref] = 1

        if type_name and type_name.endswith(".CONTENT"):
            segment_name = type_name.split(".")[0]
            items: List[Tuple[str, int | str, int | str]] = []
            for el in seq.findall(f"{XS_NS}element"):
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
                sequences[segment_name] = items

    return occurs, sequences


@lru_cache(maxsize=8)
def _load_segment_occurs_map(base_dir: str, base_prefix: str) -> Dict[str, int | str]:
    occurs, _ = _load_segments_info(base_dir, base_prefix)
    return occurs


@lru_cache(maxsize=8)
def _load_segment_sequences(
    base_dir: str, base_prefix: str
) -> Dict[str, List[Tuple[str, int | str, int | str]]]:
    _, sequences = _load_segments_info(base_dir, base_prefix)
    return sequences


def _parse_occurs_attr(max_occurs_attr: str | None) -> int | str:
    if max_occurs_attr is None:
        return 1
    if max_occurs_attr == "unbounded":
        return "unbounded"
    try:
        return int(max_occurs_attr)
    except ValueError:
        return 1


@lru_cache(maxsize=8)
def _load_inline_schema_maps(
    structure_xsd_path: str,
) -> Tuple[
    Dict[str, str],
    Dict[str, List[str]],
    Dict[str, str],
    Dict[str, int | str],
    Dict[str, List[Tuple[str, int | str, int | str]]],
]:
    """
    Build the same field-type/segment-sequence maps as ``_load_hl7_type_maps`` /
    ``_load_segment_occurs_map`` / ``_load_segment_sequences``, but from a single
    self-contained structure XSD.

    Some structure schemas (e.g. RISP's ORU_R01/OMG_O19) declare every segment and
    component type inline in one file using ``name``/``type`` attributes, rather
    than referencing shared ``<prefix>_fields.xsd`` / ``<prefix>_segments.xsd`` /
    ``<prefix>_types.xsd`` files via ``ref``. This walks every ``complexType`` in
    the document once and derives the equivalent maps directly from it.
    """
    root = ET.parse(structure_xsd_path).getroot()

    element_to_type: Dict[str, str] = {}
    element_max_occurs: Dict[str, int | str] = {}
    type_children: Dict[str, List[str]] = {}
    segment_sequences: Dict[str, List[Tuple[str, int | str, int | str]]] = {}

    for ctype in root.findall(f"{XS_NS}complexType"):
        type_name = ctype.get("name")
        seq = ctype.find(f"{XS_NS}sequence")
        if not type_name or seq is None:
            continue

        children: List[str] = []
        sequence_items: List[Tuple[str, int | str, int | str]] = []
        for el in seq.findall(f"{XS_NS}element"):
            name = el.get("name")
            if not name:
                continue
            type_attr = el.get("type")
            if type_attr:
                element_to_type[name] = type_attr

            min_occurs_attr = el.get("minOccurs")
            min_occurs: int | str = int(min_occurs_attr) if min_occurs_attr else 1
            max_occurs = _parse_occurs_attr(el.get("maxOccurs"))

            element_max_occurs[name] = max_occurs
            children.append(name)
            sequence_items.append((name, min_occurs, max_occurs))

        if children:
            type_children[type_name] = children
        # In this inline style, segment-level complex types are named after the bare
        # segment tag (e.g. "PID", "MSH") rather than "<segment>.CONTENT".
        # Component/group types always contain a '.' in their name, so this
        # distinguishes segments without needing a separate naming convention.
        if "." not in type_name and sequence_items:
            segment_sequences[type_name] = sequence_items

    type_base: Dict[str, str] = {}
    return element_to_type, type_children, type_base, element_max_occurs, segment_sequences


