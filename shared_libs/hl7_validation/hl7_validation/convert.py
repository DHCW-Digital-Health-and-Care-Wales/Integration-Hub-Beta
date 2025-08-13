from typing import Dict, List, Optional
from xml.etree.ElementTree import Element as XElem
from xml.etree.ElementTree import tostring

from hl7apy.parser import parse_message

from .utils.extract_string import _get_field_text
from .utils.xml_schema_maps import (
    _load_hl7_type_maps,
    _load_segment_occurs_map,
    _load_segment_sequences,
)
from .utils.structure_detection import (
    _load_message_structure,
    _resolve_base_dir,
    _detect_base_prefix,
)


def er7_to_hl7v2xml(er7_message: str, structure_xsd_path: Optional[str] = None) -> str:
    ns = "urn:hl7-org:v2xml"
    hl7_msg = parse_message(er7_message, find_groups=False)

    base_dir = _resolve_base_dir(structure_xsd_path)
    base_prefix = _detect_base_prefix(structure_xsd_path)
    element_to_type, type_children, type_base = _load_hl7_type_maps(
        base_dir, base_prefix
    )
    element_max_occurs = _load_segment_occurs_map(base_dir, base_prefix)
    segment_sequences = _load_segment_sequences(base_dir, base_prefix)

    def q(tag: str) -> str:
        return f"{{{ns}}}{tag}"

    def resolve_type_children(type_name: Optional[str]) -> List[str]:
        if not type_name:
            return []
        seen: set[str] = set()
        current = type_name
        while current and current not in seen:
            seen.add(current)
            children = type_children.get(current)
            if children:
                return children
            current = type_base.get(current)
        return []

    def emit_element(parent: XElem, element_name: str, raw_value: str) -> None:
        elem = XElem(q(element_name))
        parent.append(elem)

        type_name = element_to_type.get(element_name)
        children = resolve_type_children(type_name)
        if not children:
            if raw_value:
                elem.text = raw_value
            return

        components = raw_value.split("^") if raw_value else []
        for idx, child_element_name in enumerate(children):
            component_value = components[idx] if idx < len(components) else ""
            emit_element(elem, child_element_name, component_value)

    def emit_field(
        parent: XElem, segment_name: str, field_number: int, raw_value: str
    ) -> None:
        field_element_name = f"{segment_name}.{field_number}"
        if segment_name == "MSH" and field_number == 2:
            emit_element(parent, field_element_name, raw_value)
            return
        occ = element_max_occurs.get(field_element_name, 1)
        allows_repetition = (occ == "unbounded") or (isinstance(occ, int) and occ > 1)
        reps = (
            raw_value.split("~")
            if (raw_value and allows_repetition)
            else [raw_value or ""]
        )
        for rep in reps:
            emit_element(parent, field_element_name, rep)

    structure_id = (getattr(hl7_msg.msh.msh_9.msh_9_3, "value", None) or "").strip()
    if not structure_id:
        raise ValueError(
            "Unable to determine message structure (MSH-9.3) from ER7 message"
        )

    group_children_map: Dict[str, List[str]] = {}
    group_first_child: Dict[str, str] = {}
    if structure_xsd_path:
        _, group_children_map = _load_message_structure(
            structure_xsd_path, structure_id
        )
        for gname, children in group_children_map.items():
            if children:
                group_first_child[gname] = children[0]

    root = XElem(q(structure_id))
    current_group_node: XElem | None = None
    current_group_name: Optional[str] = None

    for segment in hl7_msg.children:
        seg_tag = str(segment.name)

        if group_children_map:
            allowed_current = (
                set(group_children_map.get(current_group_name or "", []))
                if current_group_name
                else set()
            )
            candidate_group_name: Optional[str] = None
            for gname, first_child in group_first_child.items():
                if seg_tag == first_child:
                    candidate_group_name = gname
                    break

            if current_group_name is not None:
                if seg_tag in allowed_current:
                    if candidate_group_name == current_group_name:
                        current_group_node = XElem(q(current_group_name))
                        root.append(current_group_node)
                else:
                    current_group_name = None
                    current_group_node = None
                    if candidate_group_name is not None:
                        current_group_name = candidate_group_name
                        current_group_node = XElem(q(current_group_name))
                        root.append(current_group_node)
            else:
                if candidate_group_name is not None:
                    current_group_name = candidate_group_name
                    current_group_node = XElem(q(current_group_name))
                    root.append(current_group_node)

            target_parent = (
                current_group_node if current_group_node is not None else root
            )
        else:
            target_parent = root

        seg_node = XElem(q(seg_tag))
        target_parent.append(seg_node)

        field_number_to_texts: Dict[int, List[str]] = {}
        for child in segment.children:
            name = str(child.name)
            if "_" in name:
                part = name.split("_")[1]
                if part.isdigit():
                    idx = int(part)
                    field_number_to_texts.setdefault(idx, []).append(
                        _get_field_text(child)
                    )

        sequence_items = segment_sequences.get(seg_tag, [])
        if not sequence_items:
            for idx in sorted(field_number_to_texts.keys()):
                values = field_number_to_texts[idx]
                if not values:
                    continue
                occ = element_max_occurs.get(f"{seg_tag}.{idx}", 1)
                allows_repetition = occ == "unbounded" or (
                    isinstance(occ, int) and occ > 1
                )
                if allows_repetition:
                    for val in values:
                        emit_field(seg_node, seg_tag, idx, val)
                else:
                    emit_field(seg_node, seg_tag, idx, values[0])
        else:
            for ref_name, min_occurs, max_occurs in sequence_items:
                # ref_name like 'MRG.1' -> extract index
                try:
                    idx_str = ref_name.split(".")[1]
                    idx = int(idx_str)
                except Exception:
                    continue
                values = field_number_to_texts.get(idx, [])
                allows_repetition = max_occurs == "unbounded" or (
                    isinstance(max_occurs, int) and max_occurs > 1
                )
                if values:
                    if allows_repetition:
                        for val in values:
                            emit_field(seg_node, seg_tag, idx, val)
                    else:
                        emit_field(seg_node, seg_tag, idx, values[0])
                else:
                    required_count = min_occurs if isinstance(min_occurs, int) else 1
                    for _ in range(required_count):
                        emit_field(seg_node, seg_tag, idx, "")

    return tostring(root, encoding="unicode")
