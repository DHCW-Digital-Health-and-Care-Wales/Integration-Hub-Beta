"""Parse an HL7 structure XSD into a recursive grammar tree and field/type maps.

Two XSD "shapes" are handled, both used today under shared_libs/hl7_message_processor
(see notes/hl7-message-processor-design-report.md section 2.1):

- **Modular** (``schemas/<version>/<version>_<STRUCTURE>.xsd``): includes a shared
  ``<version>_segments.xsd`` and declares message groups as top-level ``<xsd:complexType
  name="X.CONTENT">`` types, referenced via ``<xsd:element ref="X"/>``.
- **Self-contained** (``custom_schemas/<version>/<STRUCTURE>_<version>.xsd``): a single file with every
  segment/group/component declared inline (``name=``/``type=``), no ``<xsd:include>``.

Both shapes are parsed into the same recursive ``GroupItem`` tree (arbitrary depth) so the matcher in
``matcher.py`` never has to special-case which shape produced it - this is the actual fix for the
single-level "current group" defect confirmed in ``hl7_validation.convert`` (design report section 3.2).

The rule used throughout to distinguish a *group* reference from a *segment* reference is the same one
``ForTesting/hl7-rust-main`` uses for the XML->ER7 direction (design report section 4.3): a name
containing "." is a group (HL7 segment codes never contain a dot); anything else is a segment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Tuple, Union
from xml.etree.ElementTree import Element as XElem  # nosec B405

from defusedxml import ElementTree as ET

XS_NS = "{http://www.w3.org/2001/XMLSchema}"

Occurs = Union[int, str]  # int, or "unbounded"


@dataclass(frozen=True)
class SegmentItem:
    """A leaf segment reference in the grammar (e.g. "PID")."""

    name: str
    min_occurs: int
    max_occurs: Occurs


@dataclass(frozen=True)
class GroupItem:
    """A named group of items in the grammar (e.g. "ORU_R01.PATIENT_RESULT"), recursive."""

    name: str
    min_occurs: int
    max_occurs: Occurs
    items: Tuple[Union["SegmentItem", "GroupItem"], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TypeMaps:
    """Field/component decomposition maps used to render segment fields as XML."""

    element_to_type: Dict[str, str]
    type_children: Dict[str, List[str]]
    type_base: Dict[str, str]
    element_max_occurs: Dict[str, Occurs]
    segment_sequences: Dict[str, List[Tuple[int, int, Occurs]]]
    # minOccurs of a composite type's child element (e.g. "HD.2"), as declared where that child is
    # a <sequence> member of its *parent composite type* (HD, XPN, CX, ...) - NOT to be confused with
    # ``element_max_occurs``, which tracks *field*-level repetition (e.g. can "PID.3" repeat via "~").
    # Used by ``_emit_element`` to decide whether a component the raw ER7 value never supplied may be
    # omitted entirely (minOccurs=0, HL7's normal "trailing components omitted" encoding rule) or must
    # still be emitted as an empty element to satisfy the schema (minOccurs>=1).
    element_min_occurs: Dict[str, int] = field(default_factory=dict)


def _is_group_name(name: str) -> bool:
    return "." in name


def _parse_occurs(element: XElem) -> Tuple[int, Occurs]:
    min_occurs_attr = element.get("minOccurs")
    max_occurs_attr = element.get("maxOccurs")
    min_occurs = int(min_occurs_attr) if min_occurs_attr else 1
    max_occurs: Occurs
    if max_occurs_attr is None:
        max_occurs = 1
    elif max_occurs_attr == "unbounded":
        max_occurs = "unbounded"
    else:
        try:
            max_occurs = int(max_occurs_attr)
        except ValueError:
            max_occurs = 1
    return min_occurs, max_occurs


@lru_cache(maxsize=32)
def _detect_base_prefix(structure_xsd_path: str) -> str | None:
    """Detect the "<prefix>" of a modular schema's shared "<prefix>_segments.xsd" include.

    Returns None for a self-contained schema (no such include exists), so callers fall back to
    parsing the structure XSD directly.
    """
    root = ET.parse(structure_xsd_path).getroot()
    for inc in root.findall(f"{XS_NS}include"):
        loc = inc.get("schemaLocation")
        if not loc:
            continue
        filename = os.path.basename(loc)
        if filename.endswith("_segments.xsd"):
            return filename[: -len("_segments.xsd")]
    return None


@lru_cache(maxsize=64)
def load_structure_grammar(structure_xsd_path: str, structure_id: str) -> GroupItem:
    """Parse ``structure_xsd_path`` into a recursive grammar tree rooted at ``structure_id``."""
    base_prefix = _detect_base_prefix(structure_xsd_path)
    if base_prefix is not None:
        return _load_modular_grammar(structure_xsd_path, structure_id)
    return _load_inline_grammar(structure_xsd_path, structure_id)


def _load_modular_grammar(structure_xsd_path: str, structure_id: str) -> GroupItem:
    root = ET.parse(structure_xsd_path).getroot()

    # type_name -> [(ref, min_occurs, max_occurs)], recursively covers every group defined in the file
    # (both the root "<STRUCTURE>.CONTENT" type and every nested "<STRUCTURE>.<GROUP>.CONTENT" type).
    complex_sequences: Dict[str, List[Tuple[str, int, Occurs]]] = {}
    for ctype in root.findall(f"{XS_NS}complexType"):
        type_name = ctype.get("name")
        seq = ctype.find(f"{XS_NS}sequence")
        if not type_name or seq is None:
            continue
        items: List[Tuple[str, int, Occurs]] = []
        for el in seq.findall(f"{XS_NS}element"):
            ref = el.get("ref")
            if not ref:
                continue
            min_occurs, max_occurs = _parse_occurs(el)
            items.append((ref, min_occurs, max_occurs))
        if items:
            complex_sequences[type_name] = items

    def build(type_name: str) -> Tuple[Union[SegmentItem, GroupItem], ...]:
        result: List[Union[SegmentItem, GroupItem]] = []
        for ref, min_occurs, max_occurs in complex_sequences.get(type_name, []):
            if _is_group_name(ref):
                child_items = build(f"{ref}.CONTENT")
                result.append(GroupItem(ref, min_occurs, max_occurs, child_items))
            else:
                result.append(SegmentItem(ref, min_occurs, max_occurs))
        return tuple(result)

    root_items = build(f"{structure_id}.CONTENT")
    return GroupItem(structure_id, 1, 1, root_items)


def _load_inline_grammar(structure_xsd_path: str, structure_id: str) -> GroupItem:
    root = ET.parse(structure_xsd_path).getroot()
    root_element = next(
        (el for el in root.findall(f"{XS_NS}element") if el.get("name") == structure_id),
        None,
    )
    if root_element is None:
        return GroupItem(structure_id, 1, 1, ())

    def walk(element: XElem) -> Tuple[Union[SegmentItem, GroupItem], ...]:
        ctype = element.find(f"{XS_NS}complexType")
        if ctype is None:
            return ()
        seq = ctype.find(f"{XS_NS}sequence")
        if seq is None:
            return ()

        result: List[Union[SegmentItem, GroupItem]] = []
        for child_el in seq.findall(f"{XS_NS}element"):
            name = child_el.get("name")
            if not name:
                continue
            min_occurs, max_occurs = _parse_occurs(child_el)
            if child_el.get("type") is None and _is_group_name(name):
                result.append(GroupItem(name, min_occurs, max_occurs, walk(child_el)))
            else:
                result.append(SegmentItem(name, min_occurs, max_occurs))
        return tuple(result)

    return GroupItem(structure_id, 1, 1, walk(root_element))


@lru_cache(maxsize=8)
def _load_hl7_type_maps(
    base_dir: str, base_prefix: str
) -> Tuple[Dict[str, str], Dict[str, List[str]], Dict[str, str], Dict[str, int]]:
    fields_root = ET.parse(os.path.join(base_dir, f"{base_prefix}_fields.xsd")).getroot()
    types_root = ET.parse(os.path.join(base_dir, f"{base_prefix}_types.xsd")).getroot()

    element_to_type: Dict[str, str] = {}
    for parsed_root in (fields_root, types_root):
        for el in parsed_root.findall(f"{XS_NS}element"):
            name = el.get("name")
            type_name = el.get("type")
            if name and type_name:
                element_to_type[name] = type_name

    type_children: Dict[str, List[str]] = {}
    type_base: Dict[str, str] = {}
    component_min_occurs: Dict[str, int] = {}
    for ctype in types_root.findall(f"{XS_NS}complexType"):
        type_name = ctype.get("name")
        if not type_name:
            continue
        seq = ctype.find(f"{XS_NS}sequence")
        if seq is not None:
            child_names = []
            for el in seq.findall(f"{XS_NS}element"):
                ref = el.get("ref")
                if not ref:
                    continue
                child_names.append(ref)
                min_occurs, _ = _parse_occurs(el)
                component_min_occurs[ref] = min_occurs
            if child_names:
                type_children[type_name] = child_names
        complex_content = ctype.find(f"{XS_NS}complexContent")
        if complex_content is not None:
            extension = complex_content.find(f"{XS_NS}extension")
            if extension is not None and extension.get("base"):
                type_base[type_name] = extension.get("base")

    return element_to_type, type_children, type_base, component_min_occurs


@lru_cache(maxsize=8)
def _load_segments_info(
    base_dir: str, base_prefix: str
) -> Tuple[Dict[str, Occurs], Dict[str, List[Tuple[int, int, Occurs]]]]:
    root = ET.parse(os.path.join(base_dir, f"{base_prefix}_segments.xsd")).getroot()

    occurs: Dict[str, Occurs] = {}
    sequences: Dict[str, List[Tuple[int, int, Occurs]]] = {}

    for ctype in root.findall(f"{XS_NS}complexType"):
        type_name = ctype.get("name")
        seq = ctype.find(f"{XS_NS}sequence")
        if seq is None:
            continue

        for el in seq.findall(f"{XS_NS}element"):
            ref = el.get("ref")
            if ref:
                _, max_occurs = _parse_occurs(el)
                occurs[ref] = max_occurs

        if type_name and type_name.endswith(".CONTENT"):
            segment_name = type_name.split(".")[0]
            items: List[Tuple[int, int, Occurs]] = []
            for el in seq.findall(f"{XS_NS}element"):
                ref = el.get("ref")
                if not ref:
                    continue
                try:
                    field_num = int(ref.split(".")[1])
                except (IndexError, ValueError):
                    continue
                min_occurs, max_occurs = _parse_occurs(el)
                items.append((field_num, min_occurs, max_occurs))
            if items:
                sequences[segment_name] = items

    return occurs, sequences


@lru_cache(maxsize=8)
def _load_inline_type_maps(structure_xsd_path: str) -> TypeMaps:
    """Derive the same maps as the modular loaders, but from a single self-contained XSD.

    Self-contained schemas (custom_schemas/) declare every segment/component type inline via
    ``name``/``type`` attributes rather than shared ``ref``-based includes.
    """
    root = ET.parse(structure_xsd_path).getroot()

    element_to_type: Dict[str, str] = {}
    element_max_occurs: Dict[str, Occurs] = {}
    type_children: Dict[str, List[str]] = {}
    segment_sequences: Dict[str, List[Tuple[int, int, Occurs]]] = {}
    component_min_occurs: Dict[str, int] = {}

    for ctype in root.findall(f"{XS_NS}complexType"):
        type_name = ctype.get("name")
        seq = ctype.find(f"{XS_NS}sequence")
        if not type_name or seq is None:
            continue

        children: List[str] = []
        for el in seq.findall(f"{XS_NS}element"):
            name = el.get("name")
            if not name:
                continue
            type_attr = el.get("type")
            if type_attr:
                element_to_type[name] = type_attr
            min_occurs, max_occurs = _parse_occurs(el)
            element_max_occurs[name] = max_occurs
            component_min_occurs[name] = min_occurs
            children.append(name)

        if children:
            type_children[type_name] = children

        # Segment-level complex types are named after the bare segment tag (e.g. "PID"); component/
        # group types always contain a "." - this distinguishes them without a separate convention.
        if "." not in type_name:
            items: List[Tuple[int, int, Occurs]] = []
            for el in seq.findall(f"{XS_NS}element"):
                name = el.get("name")
                if not name:
                    continue
                try:
                    field_num = int(name.split(".")[1])
                except (IndexError, ValueError):
                    continue
                min_occurs, max_occurs = _parse_occurs(el)
                items.append((field_num, min_occurs, max_occurs))
            if items:
                segment_sequences[type_name] = items

    return TypeMaps(element_to_type, type_children, {}, element_max_occurs, segment_sequences, component_min_occurs)


def load_type_maps(structure_xsd_path: str) -> TypeMaps:
    """Load the field/component decomposition maps for ``structure_xsd_path`` (either XSD shape)."""
    base_prefix = _detect_base_prefix(structure_xsd_path)
    if base_prefix is None:
        return _load_inline_type_maps(structure_xsd_path)

    base_dir = os.path.dirname(structure_xsd_path)
    element_to_type, type_children, type_base, component_min_occurs = _load_hl7_type_maps(base_dir, base_prefix)
    element_max_occurs, segment_sequences = _load_segments_info(base_dir, base_prefix)
    return TypeMaps(
        element_to_type, type_children, type_base, element_max_occurs, segment_sequences, component_min_occurs
    )
