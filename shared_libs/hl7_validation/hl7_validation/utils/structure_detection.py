from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from defusedxml import ElementTree as ET


def _resolve_base_dir(structure_xsd_path: Optional[str]) -> str:
    if structure_xsd_path:
        return os.path.dirname(structure_xsd_path)
    raise ValueError(
        "structure_xsd_path is required to resolve base HL7 XSDs; no default flow will be used"
    )


@lru_cache(maxsize=32)
def _detect_base_prefix(structure_xsd_path: Optional[str]) -> str:
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
    raise FileNotFoundError(
        "Unable to determine base XSD prefix from structure; expected include of '<prefix>_segments.xsd'"
    )


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

    return root_sequence, group_children_map


def _load_segment_group_paths(
    structure_xsd_path: str,
    structure_id: str,
) -> Tuple[Dict[str, List[List[str]]], Dict[Tuple[str, ...], str]]:
    """
    Build a segment->group path map for standalone structure XSDs that use nested
    inline group elements (e.g. ORU_R01.PATIENT_RESULT).
    """
    tree = ET.parse(structure_xsd_path)
    root = tree.getroot()
    xs = "{http://www.w3.org/2001/XMLSchema}"

    top = None
    for el in root.findall(f"{xs}element"):
        if el.get("name") == structure_id:
            top = el
            break
    if top is None:
        return {}

    top_seq = top.find(f"{xs}complexType/{xs}sequence")
    if top_seq is None:
        return {}

    segment_group_paths: Dict[str, List[List[str]]] = {}
    group_first_segment: Dict[Tuple[str, ...], str] = {}

    def _first_descendant_segment(sequence_el) -> str | None:
        for child in sequence_el.findall(f"{xs}element"):
            child_name = child.get("name") or child.get("ref")
            if not child_name:
                continue
            nested_seq = child.find(f"{xs}complexType/{xs}sequence")
            if "." not in child_name:
                return child_name
            if nested_seq is not None:
                nested_first = _first_descendant_segment(nested_seq)
                if nested_first:
                    return nested_first
        return None

    def _walk(sequence_el, group_path: List[str]) -> None:
        for child in sequence_el.findall(f"{xs}element"):
            child_name = child.get("name") or child.get("ref")
            if not child_name:
                continue

            nested_seq = child.find(f"{xs}complexType/{xs}sequence")

            if "." in child_name and nested_seq is not None:
                new_path = [*group_path, child_name]
                first_segment = _first_descendant_segment(nested_seq)
                if first_segment:
                    group_first_segment[tuple(new_path)] = first_segment
                _walk(nested_seq, new_path)
                continue

            if "." not in child_name:
                segment_group_paths.setdefault(child_name, []).append(group_path.copy())

    _walk(top_seq, [])
    return segment_group_paths, group_first_segment
