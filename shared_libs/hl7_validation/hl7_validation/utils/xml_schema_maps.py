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


@lru_cache(maxsize=16)
def _load_maps_from_structure_xsd(
    structure_xsd_path: str,
) -> Tuple[
    Dict[str, str],
    Dict[str, List[str]],
    Dict[str, str],
    Dict[str, int | str],
    Dict[str, List[Tuple[str, int | str, int | str]]],
]:
    root = ET.parse(structure_xsd_path).getroot()

    element_to_type: Dict[str, str] = {}
    type_children: Dict[str, List[str]] = {}
    type_base: Dict[str, str] = {}
    element_max_occurs: Dict[str, int | str] = {}
    segment_sequences: Dict[str, List[Tuple[str, int | str, int | str]]] = {}

    # Standalone schemas often declare fields and composites inline; collect every typed element.
    for el in root.iterfind(f".//{XS_NS}element"):
        name = el.get("name")
        type_name = el.get("type")
        if name and type_name:
            element_to_type[name] = type_name
            continue

        if not name:
            continue

        inline_ctype = el.find(f"{XS_NS}complexType")
        if inline_ctype is None:
            continue
        inline_seq = inline_ctype.find(f"{XS_NS}sequence")
        if inline_seq is None:
            continue

        inline_children: List[str] = []
        for child_el in inline_seq.findall(f"{XS_NS}element"):
            child_name = child_el.get("ref") or child_el.get("name")
            if child_name:
                inline_children.append(child_name)

        if inline_children:
            inline_type_name = f"__inline__.{name}"
            element_to_type[name] = inline_type_name
            type_children[inline_type_name] = inline_children

    for ctype in root.findall(f"{XS_NS}complexType"):
        type_name = ctype.get("name")
        if not type_name:
            continue

        seq = ctype.find(f"{XS_NS}sequence")
        if seq is not None:
            child_names: List[str] = []
            seq_items: List[Tuple[str, int | str, int | str]] = []
            for child_el in seq.findall(f"{XS_NS}element"):
                child_name = child_el.get("ref") or child_el.get("name")
                if not child_name:
                    continue

                child_names.append(child_name)

                min_occurs_attr = child_el.get("minOccurs")
                max_occurs_attr = child_el.get("maxOccurs")
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

                element_max_occurs[child_name] = max_occurs
                seq_items.append((child_name, min_occurs, max_occurs))

            if child_names:
                type_children[type_name] = child_names

            # Segment complex types are typically named like MSH/PID/PV1 and contain fields like PID.1, PID.3...
            if (
                seq_items
                and "." not in type_name
                and any("." in child for child, _, _ in seq_items)
                and all(child.split(".")[0] == type_name for child, _, _ in seq_items if "." in child)
            ):
                segment_sequences[type_name] = seq_items

        cc = ctype.find(f"{XS_NS}complexContent")
        if cc is not None:
            ext = cc.find(f"{XS_NS}extension")
            if ext is not None and ext.get("base"):
                type_base[type_name] = ext.get("base")  # type: ignore[arg-type]

    return (
        element_to_type,
        type_children,
        type_base,
        element_max_occurs,
        segment_sequences,
    )
