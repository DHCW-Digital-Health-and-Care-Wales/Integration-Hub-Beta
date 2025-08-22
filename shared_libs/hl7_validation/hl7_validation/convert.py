from collections import defaultdict
from typing import DefaultDict, Dict, List, Optional, Set, Tuple, Union
from xml.etree.ElementTree import Element as XElem  # nosec B405

from defusedxml import defuse_stdlib
from defusedxml.ElementTree import tostring

from .utils.extract_string import _get_field_text
from .utils.structure_detection import (
    _detect_base_prefix,
    _load_message_structure,
    _resolve_base_dir,
)
from .utils.xml_schema_maps import (
    _load_hl7_type_maps,
    _load_segment_occurs_map,
    _load_segment_sequences,
)
from .utils.message_utils import (
    extract_message_structure,
    extract_msh7_datetime,
    parse_er7_message,
)

defuse_stdlib()

HL7_XML_NAMESPACE = "urn:hl7-org:v2xml"

STRUCTURE_ERROR_MSG = "Unable to determine structure (MSH-9.3) from ER7 message"


def _qname(tag: str) -> str:
    return f"{{{HL7_XML_NAMESPACE}}}{tag}"


def _allows_repetition(max_occurs) -> bool:
    return max_occurs == "unbounded" or (
        isinstance(max_occurs, int) and max_occurs > 1
    )


def _resolve_type_children(
    type_name: Optional[str],
    type_children: Dict[str, List[str]],
    type_base: Dict[str, str]
) -> List[str]:
    if not type_name:
        return []

    seen: Set[str] = set()
    current: Optional[str] = type_name

    while current is not None and current not in seen:
        key: str = current
        seen.add(key)
        children = type_children.get(key)
        if children:
            return children
        current = type_base.get(key)
    return []


def _emit_element(
    parent: XElem,
    element_name: str,
    raw_value: str,
    element_to_type: Dict[str, str],
    type_children: Dict[str, List[str]],
    type_base: Dict[str, str]
) -> None:
    elem = XElem(_qname(element_name))
    parent.append(elem)

    type_name = element_to_type.get(element_name)
    children = _resolve_type_children(type_name, type_children, type_base)

    if not children:
        if raw_value:
            elem.text = raw_value
        return

    components = raw_value.split("^") if raw_value else []
    for idx, child_element_name in enumerate(children):
        component_value = components[idx] if idx < len(components) else ""
        _emit_element(elem, child_element_name, component_value, element_to_type, type_children, type_base)


def _emit_field(
    parent: XElem,
    segment_name: str,
    field_number: int,
    raw_value: str,
    element_to_type: Dict[str, str],
    type_children: Dict[str, List[str]],
    type_base: Dict[str, str],
    element_max_occurs: Dict[str, Union[int, str]]
) -> None:
    field_element_name = f"{segment_name}.{field_number}"

    if segment_name == "MSH" and field_number == 2:
        _emit_element(parent, field_element_name, raw_value, element_to_type, type_children, type_base)
        return

    max_occurs = element_max_occurs.get(field_element_name, 1)
    reps = (
        raw_value.split("~")
        if raw_value and _allows_repetition(max_occurs)
        else [raw_value or ""]
    )

    for rep in reps:
        _emit_element(parent, field_element_name, rep, element_to_type, type_children, type_base)


def _extract_field_data(segment) -> Dict[int, str]:
    field_map = defaultdict(list)
    for child in segment.children:
        try:
            field_index = int(str(child.name).split("_")[1])
            field_map[field_index].append(_get_field_text(child))
        except (ValueError, IndexError):
            continue
    return {idx: "~".join(vals) for idx, vals in field_map.items()}


def _get_field_specs(
    seg_tag: str,
    field_data: Dict[int, str],
    segment_sequences: Dict[str, List[Tuple[str, Union[int, str], Union[int, str]]]],
    element_max_occurs: Dict[str, Union[int, str]]
) -> List[Tuple[int, str, int, Union[int, str]]]:
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


def _process_fields(
    seg_node: XElem,
    seg_tag: str,
    field_data: Dict[int, str],
    element_to_type: Dict[str, str],
    type_children: Dict[str, List[str]],
    type_base: Dict[str, str],
    segment_sequences: Dict[str, List[Tuple[str, Union[int, str], Union[int, str]]]],
    element_max_occurs: Dict[str, Union[int, str]]
) -> None:
    field_specs = _get_field_specs(seg_tag, field_data, segment_sequences, element_max_occurs)
    for idx, value, required_count, _ in field_specs:
        if value:
            _emit_field(
                seg_node, seg_tag, idx, value,
                element_to_type, type_children, type_base, element_max_occurs
            )
        else:
            for _ in range(required_count):
                _emit_field(
                    seg_node, seg_tag, idx, "",
                    element_to_type, type_children, type_base, element_max_occurs
                )


def _update_group_context(
    seg_tag: str,
    group_children_map: Dict[str, Set[str]],
    group_first_child: Dict[str, str],
    current_group_name: Optional[str],
) -> Tuple[Optional[str], Optional[XElem]]:
    if not group_children_map:
        return None, None

    candidate_group_name = next(
        (gname for gname, fchild in group_first_child.items() if seg_tag == fchild),
        None,
    )

    if not current_group_name:
        new_node = XElem(_qname(candidate_group_name)) if candidate_group_name else None
        return candidate_group_name, new_node

    allowed_in_current_group: Set[str] = group_children_map.get(
        current_group_name or "", set()
    )
    if (
        seg_tag in allowed_in_current_group
        and candidate_group_name != current_group_name
    ):
        return current_group_name, None

    new_node = XElem(_qname(candidate_group_name)) if candidate_group_name else None
    return candidate_group_name, new_node


def _insert_required_segment(
    parent: XElem,
    seg_tag: str,
    fields: List[Tuple[int, str]],
    element_to_type: Dict[str, str],
    type_children: Dict[str, List[str]],
    type_base: Dict[str, str],
    element_max_occurs: Dict[str, Union[int, str]]
):
    node = XElem(_qname(seg_tag))
    parent.append(node)
    for field_num, field_val in fields:
        _emit_field(
            node, seg_tag, field_num, field_val,
            element_to_type, type_children, type_base, element_max_occurs
        )


def _maybe_insert_required_segments(
    root: XElem,
    seg_tag: str,
    msh7_value: str,
    required: Dict[str, bool],
    seen: Dict[str, bool],
    root_order: List[str],
    pv1_idx: Optional[int],
    element_to_type: Dict[str, str],
    type_children: Dict[str, List[str]],
    type_base: Dict[str, str],
    element_max_occurs: Dict[str, Union[int, str]]
) -> None:
    if (
        required.get("EVN")
        and not seen.get("EVN")
        and seg_tag not in ("MSH", "SFT", "EVN")
    ):
        _insert_required_segment(
            root, "EVN", [(2, msh7_value)],
            element_to_type, type_children, type_base, element_max_occurs
        )
        seen["EVN"] = True

    if (
        required.get("PV1")
        and not seen.get("PV1")
        and pv1_idx is not None
        and seg_tag != "PV1"
    ):
        seg_idx = (
            root_order.index(seg_tag) if seg_tag in root_order else float("inf")
        )
        if seg_idx > pv1_idx:
            _insert_required_segment(
                root, "PV1", [(2, "U")],
                element_to_type, type_children, type_base, element_max_occurs
            )
            seen["PV1"] = True


def er7_to_hl7v2xml(
    er7_message: str,
    structure_xsd_path: Optional[str] = None,
    override_structure_id: Optional[str] = None,
) -> str:
    hl7_msg = parse_er7_message(er7_message, find_groups=False)

    base_dir = _resolve_base_dir(structure_xsd_path)
    base_prefix = _detect_base_prefix(structure_xsd_path)
    element_to_type, type_children, type_base = _load_hl7_type_maps(
        base_dir, base_prefix
    )
    element_max_occurs = _load_segment_occurs_map(base_dir, base_prefix)
    segment_sequences = _load_segment_sequences(base_dir, base_prefix)

    structure_id = extract_message_structure(hl7_msg)
    if not structure_id and override_structure_id:
        structure_id = override_structure_id.strip()
    if not structure_id:
        raise ValueError(STRUCTURE_ERROR_MSG)

    group_children_map: Dict[str, List[str]] = {}
    group_first_child: Dict[str, str] = {}
    root_order: List[str] = []
    required = {"EVN": False, "PV1": False}

    if structure_xsd_path:
        root_sequence, group_children_map = _load_message_structure(
            structure_xsd_path, structure_id
        )
        group_first_child = {
            gname: children[0]
            for gname, children in group_children_map.items()
            if children
        }

        if root_sequence:
            root_order = [ref for ref, _, _ in root_sequence]
            for ref_name, min_occurs, _ in root_sequence:
                if ref_name in required:
                    required[ref_name] = isinstance(min_occurs, int) and min_occurs >= 1

    group_children_sets: Dict[str, Set[str]] = {
        name: set(children) for name, children in group_children_map.items()
    }
    pv1_idx: Optional[int] = None
    if root_order:
        try:
            pv1_idx = root_order.index("PV1")
        except ValueError:
            pv1_idx = None

    root = XElem(_qname(structure_id))
    current_group_name, current_group_node = None, None
    seen: DefaultDict[str, bool] = defaultdict(bool)
    msh7_value = extract_msh7_datetime(hl7_msg)

    for segment in hl7_msg.children:
        seg_tag = str(segment.name)

        new_group_name, new_group_node = _update_group_context(
            seg_tag, group_children_sets, group_first_child, current_group_name
        )

        if new_group_node is not None:
            current_group_node = new_group_node
            root.append(current_group_node)
        elif new_group_name != current_group_name:
            current_group_node = None

        current_group_name = new_group_name
        target_parent = current_group_node if current_group_node is not None else root

        _maybe_insert_required_segments(
            root, seg_tag, msh7_value, required, seen, root_order, pv1_idx,
            element_to_type, type_children, type_base, element_max_occurs
        )

        seg_node = XElem(_qname(seg_tag))
        target_parent.append(seg_node)

        field_data = _extract_field_data(segment)
        _process_fields(
            seg_node, seg_tag, field_data,
            element_to_type, type_children, type_base, segment_sequences, element_max_occurs
        )

        if seg_tag in required:
            seen[seg_tag] = True

    if required.get("PV1") and not seen.get("PV1"):
        _insert_required_segment(
            root, "PV1", [(2, "U")],
            element_to_type, type_children, type_base, element_max_occurs
        )

    return tostring(root, encoding="unicode")
