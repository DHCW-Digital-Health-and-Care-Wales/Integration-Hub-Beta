from typing import Dict, List, Optional, Tuple
from collections import defaultdict
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


def er7_to_hl7v2xml(
    er7_message: str,
    structure_xsd_path: Optional[str] = None,
    override_structure_id: Optional[str] = None,
) -> str:
    ns = "urn:hl7-org:v2xml"
    hl7_msg = parse_message(er7_message, find_groups=False)
    
    base_dir = _resolve_base_dir(structure_xsd_path)
    base_prefix = _detect_base_prefix(structure_xsd_path)
    element_to_type, type_children, type_base = _load_hl7_type_maps(base_dir, base_prefix)
    element_max_occurs = _load_segment_occurs_map(base_dir, base_prefix)
    segment_sequences = _load_segment_sequences(base_dir, base_prefix)

    def q(tag: str) -> str:
        return f"{{{ns}}}{tag}"

    def allows_repetition(max_occurs) -> bool:
        return max_occurs == "unbounded" or (isinstance(max_occurs, int) and max_occurs > 1)

    def resolve_type_children(type_name: Optional[str]) -> List[str]:
        if not type_name:
            return []
        seen = set()
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

    def emit_field(parent: XElem, segment_name: str, field_number: int, raw_value: str) -> None:
        field_element_name = f"{segment_name}.{field_number}"
        
        if segment_name == "MSH" and field_number == 2:
            emit_element(parent, field_element_name, raw_value)
            return
        
        max_occurs = element_max_occurs.get(field_element_name, 1)
        reps = raw_value.split("~") if raw_value and allows_repetition(max_occurs) else [raw_value or ""]
        
        for rep in reps:
            emit_element(parent, field_element_name, rep)

    def extract_field_data(segment) -> Dict[int, str]:
        field_map = defaultdict(list)
        for child in segment.children:
            try:
                field_index = int(str(child.name).split('_')[1])
                field_map[field_index].append(_get_field_text(child))
            except (ValueError, IndexError):
                continue
        return {idx: "~".join(vals) for idx, vals in field_map.items()}

    def get_field_specs(seg_tag: str, field_data: Dict[int, str]) -> List[Tuple[int, str, int, str]]:
        sequence_items = segment_sequences.get(seg_tag, [])
        specs = []
        
        if sequence_items:
            for ref_name, min_occurs, max_occurs in sequence_items:
                try:
                    idx = int(ref_name.split(".")[1])
                except (IndexError, ValueError):
                    continue
                value = field_data.get(idx, "")
                required_count = min_occurs if isinstance(min_occurs, int) else 0
                specs.append((idx, value, required_count, max_occurs))
        else:
            for idx in sorted(field_data.keys()):
                value = field_data[idx]
                if value:
                    max_occurs = element_max_occurs.get(f"{seg_tag}.{idx}", 1)
                    specs.append((idx, value, 0, max_occurs))
        return specs

    def process_fields(seg_node: XElem, seg_tag: str, field_data: Dict[int, str]) -> None:
        field_specs = get_field_specs(seg_tag, field_data)
        for idx, value, required_count, _ in field_specs:
            if value:
                emit_field(seg_node, seg_tag, idx, value)
            else:
                for _ in range(required_count):
                    emit_field(seg_node, seg_tag, idx, "")
    
    def update_group_context(seg_tag: str, group_children_map: Dict[str, List[str]], 
                           group_first_child: Dict[str, str], current_group_name: Optional[str]) -> Tuple[Optional[str], Optional[XElem]]:
        if not group_children_map:
            return None, None
            
        candidate_group_name = next((gname for gname, fchild in group_first_child.items() if seg_tag == fchild), None)

        if not current_group_name:
            new_node = XElem(q(candidate_group_name)) if candidate_group_name else None
            return candidate_group_name, new_node

        allowed_in_current_group = group_children_map.get(current_group_name, set())
        if seg_tag in allowed_in_current_group and candidate_group_name != current_group_name:
            return current_group_name, None

        new_node = XElem(q(candidate_group_name)) if candidate_group_name else None
        return candidate_group_name, new_node

    def _insert_required_segment(parent: XElem, seg_tag: str, fields: List[Tuple[int, str]]):
        node = XElem(q(seg_tag))
        parent.append(node)
        for field_num, field_val in fields:
            emit_field(node, seg_tag, field_num, field_val)
    
    def maybe_insert_required_segments(root: XElem, seg_tag: str, msh7_value: str, 
                                     required: Dict[str, bool], seen: Dict[str, bool], 
                                     root_order: List[str], pv1_idx: Optional[int]) -> None:
        if required.get("EVN") and not seen.get("EVN") and seg_tag not in ("MSH", "SFT", "EVN"):
            _insert_required_segment(root, "EVN", [(2, msh7_value)])
            seen["EVN"] = True

        if required.get("PV1") and not seen.get("PV1") and pv1_idx is not None and seg_tag != "PV1":
            seg_idx = root_order.index(seg_tag) if seg_tag in root_order else float('inf')
            if seg_idx > pv1_idx:
                _insert_required_segment(root, "PV1", [(2, "U")])
                seen["PV1"] = True

    structure_id = (getattr(hl7_msg.msh.msh_9.msh_9_3, "value", None) or "").strip()
    if not structure_id and override_structure_id:
        structure_id = override_structure_id.strip()
    if not structure_id:
        raise ValueError("Unable to determine message structure (MSH-9.3) from ER7 message")

    group_children_map, group_first_child, root_order = {}, {}, []
    required = {"EVN": False, "PV1": False}
    
    if structure_xsd_path:
        root_sequence, group_children_map = _load_message_structure(structure_xsd_path, structure_id)
        group_first_child = {gname: children[0] for gname, children in group_children_map.items() if children}
        
        if root_sequence:
            root_order = [ref for ref, _, _ in root_sequence]
            for ref_name, min_occurs, _ in root_sequence:
                if ref_name in required:
                    required[ref_name] = isinstance(min_occurs, int) and min_occurs >= 1

    group_children_sets = {name: set(children) for name, children in group_children_map.items()}
    pv1_idx: Optional[int] = None
    if root_order:
        try:
            pv1_idx = root_order.index("PV1")
        except ValueError:
            pv1_idx = None

    root = XElem(q(structure_id))
    current_group_name, current_group_node = None, None
    seen = defaultdict(bool)
    msh7_value = (getattr(hl7_msg.msh.msh_7, "value", None) or "").strip()

    for segment in hl7_msg.children:
        seg_tag = str(segment.name)

        new_group_name, new_group_node = update_group_context(
            seg_tag, group_children_sets, group_first_child, current_group_name
        )
        
        if new_group_node is not None:
            current_group_node = new_group_node
            root.append(current_group_node)
        elif new_group_name != current_group_name:
            current_group_node = None
        
        current_group_name = new_group_name
        target_parent = current_group_node if current_group_node is not None else root

        maybe_insert_required_segments(
            root, seg_tag, msh7_value, required, seen, root_order, pv1_idx
        )

        seg_node = XElem(q(seg_tag))
        target_parent.append(seg_node)
        
        field_data = extract_field_data(segment)
        process_fields(seg_node, seg_tag, field_data)

        if seg_tag in required:
            seen[seg_tag] = True

    if required.get("PV1") and not seen.get("PV1"):
        _insert_required_segment(root, "PV1", [(2, "U")])

    return tostring(root, encoding="unicode")
