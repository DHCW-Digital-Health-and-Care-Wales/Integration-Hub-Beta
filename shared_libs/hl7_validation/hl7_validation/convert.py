from collections import defaultdict
from functools import lru_cache
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple, Union
from xml.etree.ElementTree import Element as XElem  # nosec B405

from defusedxml import defuse_stdlib
from defusedxml.ElementTree import fromstring, tostring
from hl7apy.core import Message

from .utils.extract_string import _get_field_text
from .utils.message_utils import (
    extract_message_structure,
    extract_msh7_datetime,
    parse_er7_message,
)
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

defuse_stdlib()

HL7_XML_NAMESPACE = "urn:hl7-org:v2xml"

STRUCTURE_ERROR_MSG = "Unable to determine structure (MSH-9.3) from ER7 message"

# HL7 segment constants
MSH_SEGMENT = "MSH"
MSH_FIELD_SEPARATOR_INDEX = 2
EVN_SEGMENT = "EVN"
PV1_SEGMENT = "PV1"
SFT_SEGMENT = "SFT"
PV1_DEFAULT_VALUE = "U"


def _qname(tag: str) -> str:
    return f"{{{HL7_XML_NAMESPACE}}}{tag}"


def _allows_repetition(max_occurs: Union[int, str]) -> bool:
    return max_occurs == "unbounded" or (isinstance(max_occurs, int) and max_occurs > 1)


def _resolve_type_children(
    type_name: Optional[str], type_children: Dict[str, List[str]], type_base: Dict[str, str]
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
    type_base: Dict[str, str],
) -> None:
    elem = XElem(_qname(element_name))
    parent.append(elem)

    type_name = element_to_type.get(element_name)
    children = _resolve_type_children(type_name, type_children, type_base)

    if not children:
        if raw_value:
            elem.text = raw_value
        return

    if raw_value:
        components = raw_value.split("^")
    else:
        components = []
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
    element_max_occurs: Dict[str, Union[int, str]],
) -> None:
    """
    Emit a field element to XML, handling repetitions and component structures.

    Special handling for MSH.2 (field separator) which doesn't support repetitions.
    """
    field_element_name = f"{segment_name}.{field_number}"

    if segment_name == MSH_SEGMENT and field_number == MSH_FIELD_SEPARATOR_INDEX:
        _emit_element(parent, field_element_name, raw_value, element_to_type, type_children, type_base)
        return

    max_occurs = element_max_occurs.get(field_element_name, 1)
    if raw_value and "~" in raw_value and _allows_repetition(max_occurs):
        reps = raw_value.split("~")
    else:
        reps = [raw_value or ""]

    for rep in reps:
        _emit_element(parent, field_element_name, rep, element_to_type, type_children, type_base)


def _extract_field_data(segment: Any) -> Dict[int, str]:
    """
    Extract field data from an HL7 segment, combining repeated values with ~ separator.

    Args:
        segment: HL7 segment object with children representing fields

    Returns:
        Dictionary mapping field index to combined field value (repetitions joined with ~)
    """
    field_map = defaultdict(list)
    for child in segment.children:
        try:
            child_name_str = str(child.name)
            if "_" in child_name_str:
                field_index = int(child_name_str.split("_")[1])
                field_map[field_index].append(_get_field_text(child))
        except (ValueError, IndexError):
            continue
    return {idx: "~".join(vals) for idx, vals in field_map.items()}


def _get_field_specs(
    seg_tag: str,
    field_data: Dict[int, str],
    segment_sequences: Dict[str, List[Tuple[str, Union[int, str], Union[int, str]]]],
    element_max_occurs: Dict[str, Union[int, str]],
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
    element_max_occurs: Dict[str, Union[int, str]],
) -> None:
    field_specs = _get_field_specs(seg_tag, field_data, segment_sequences, element_max_occurs)
    for idx, value, required_count, _ in field_specs:
        if value:
            _emit_field(seg_node, seg_tag, idx, value, element_to_type, type_children, type_base, element_max_occurs)
        else:
            for _ in range(required_count):
                _emit_field(seg_node, seg_tag, idx, "", element_to_type, type_children, type_base, element_max_occurs)


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

    allowed_in_current_group: Set[str] = group_children_map.get(current_group_name or "", set())
    if seg_tag in allowed_in_current_group and candidate_group_name != current_group_name:
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
    element_max_occurs: Dict[str, Union[int, str]],
) -> None:
    node = XElem(_qname(seg_tag))
    parent.append(node)
    for field_num, field_val in fields:
        _emit_field(node, seg_tag, field_num, field_val, element_to_type, type_children, type_base, element_max_occurs)


def insert_missing_required_segments(
    root: XElem,
    seg_tag: str,
    msh7_datetime: str,
    required: Dict[str, bool],
    seen: Dict[str, bool],
    root_order: List[str],
    pv1_idx: Optional[int],
    element_to_type: Dict[str, str],
    type_children: Dict[str, List[str]],
    type_base: Dict[str, str],
    element_max_occurs: Dict[str, Union[int, str]],
) -> None:
    """
    Insert required EVN and PV1 segments if missing from the message structure.

    EVN is inserted after MSH/SFT if required and not present.
    PV1 is inserted at the correct position in root_order if required and not present.

    Args:
        root: Root XML element
        seg_tag: Current segment tag being processed
        msh7_datetime: DateTime value from MSH.7 to use for EVN.2
        required: Dict indicating which segments are required
        seen: Dict tracking which segments have been seen
        root_order: Ordered list of segment references from schema
        pv1_idx: Index of PV1 in root_order, or None if not present
        element_to_type: Mapping of element names to type names
        type_children: Mapping of type names to child element lists
        type_base: Mapping of type names to base type names
        element_max_occurs: Mapping of element names to max occurrence counts
    """
    segments_before_evn = (MSH_SEGMENT, SFT_SEGMENT, EVN_SEGMENT)
    if required.get(EVN_SEGMENT) and not seen.get(EVN_SEGMENT) and seg_tag not in segments_before_evn:
        _insert_required_segment(
            root, EVN_SEGMENT, [(2, msh7_datetime)], element_to_type, type_children, type_base, element_max_occurs
        )
        seen[EVN_SEGMENT] = True

    if required.get(PV1_SEGMENT) and not seen.get(PV1_SEGMENT) and pv1_idx is not None and seg_tag != PV1_SEGMENT:
        seg_idx = root_order.index(seg_tag) if seg_tag in root_order else float("inf")
        if seg_idx > pv1_idx:
            _insert_required_segment(
                root,
                PV1_SEGMENT,
                [(2, PV1_DEFAULT_VALUE)],
                element_to_type,
                type_children,
                type_base,
                element_max_occurs,
            )
            seen[PV1_SEGMENT] = True


def _load_schema_maps(
    structure_xsd_path: Optional[str],
) -> Tuple[
    Dict[str, str],
    Dict[str, List[str]],
    Dict[str, str],
    Dict[str, Union[int, str]],
    Dict[str, List[Tuple[str, Union[int, str], Union[int, str]]]],
]:
    base_dir = _resolve_base_dir(structure_xsd_path)
    base_prefix = _detect_base_prefix(structure_xsd_path)
    element_to_type, type_children, type_base = _load_hl7_type_maps(base_dir, base_prefix)
    element_max_occurs = _load_segment_occurs_map(base_dir, base_prefix)
    segment_sequences = _load_segment_sequences(base_dir, base_prefix)
    return (
        element_to_type,
        type_children,
        type_base,
        element_max_occurs,
        segment_sequences,
    )


def _resolve_structure_id(hl7_msg: Any, override_structure_id: Optional[str]) -> str:
    structure_id = extract_message_structure(hl7_msg)
    if not structure_id and override_structure_id:
        structure_id = override_structure_id.strip()
    if not structure_id:
        raise ValueError(STRUCTURE_ERROR_MSG)
    return structure_id


@lru_cache(maxsize=64)
def _compute_structure_requirements(
    structure_xsd_path: Optional[str],
    structure_id: str,
) -> Tuple[
    Dict[str, Set[str]],
    Dict[str, str],
    List[str],
    Dict[str, bool],
    Optional[int],
]:
    group_children_map: Dict[str, List[str]] = {}
    group_first_child: Dict[str, str] = {}
    root_order: List[str] = []
    required: Dict[str, bool] = {EVN_SEGMENT: False, PV1_SEGMENT: False}

    if structure_xsd_path:
        root_sequence, group_children_map = _load_message_structure(structure_xsd_path, structure_id)
        group_first_child = {gname: children[0] for gname, children in group_children_map.items() if children}

        if root_sequence:
            root_order = [ref for ref, _, _ in root_sequence]
            for ref_name, min_occurs, _ in root_sequence:
                if ref_name in required:
                    required[ref_name] = isinstance(min_occurs, int) and min_occurs >= 1

    group_children_sets: Dict[str, Set[str]] = {name: set(children) for name, children in group_children_map.items()}

    pv1_idx: Optional[int] = None
    if root_order:
        try:
            pv1_idx = root_order.index(PV1_SEGMENT)
        except ValueError:
            pv1_idx = None

    return group_children_sets, group_first_child, root_order, required, pv1_idx


def _build_message_xml_tree(
    hl7_msg: Any,
    structure_id: str,
    element_to_type: Dict[str, str],
    type_children: Dict[str, List[str]],
    type_base: Dict[str, str],
    element_max_occurs: Dict[str, Union[int, str]],
    segment_sequences: Dict[str, List[Tuple[str, Union[int, str], Union[int, str]]]],
    group_children_sets: Dict[str, Set[str]],
    group_first_child: Dict[str, str],
    root_order: List[str],
    required: Dict[str, bool],
    pv1_idx: Optional[int],
) -> XElem:
    root = XElem(_qname(structure_id))
    current_group_name, current_group_node = None, None
    seen: DefaultDict[str, bool] = defaultdict(bool)
    msh7_datetime = extract_msh7_datetime(hl7_msg)

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

        insert_missing_required_segments(
            root,
            seg_tag,
            msh7_datetime,
            required,
            seen,
            root_order,
            pv1_idx,
            element_to_type,
            type_children,
            type_base,
            element_max_occurs,
        )

        seg_node = XElem(_qname(seg_tag))
        target_parent.append(seg_node)

        field_data = _extract_field_data(segment)
        _process_fields(
            seg_node,
            seg_tag,
            field_data,
            element_to_type,
            type_children,
            type_base,
            segment_sequences,
            element_max_occurs,
        )

        if seg_tag in required:
            seen[seg_tag] = True

    return root


def er7_to_hl7v2xml(
    er7_message: str,
    structure_xsd_path: Optional[str] = None,
    override_structure_id: Optional[str] = None,
    parsed_message: Optional[Message] = None,
) -> str:
    if parsed_message is not None:
        hl7_msg = parsed_message
    else:
        hl7_msg = parse_er7_message(er7_message, find_groups=False)

    (
        element_to_type,
        type_children,
        type_base,
        element_max_occurs,
        segment_sequences,
    ) = _load_schema_maps(structure_xsd_path)

    structure_id = _resolve_structure_id(hl7_msg, override_structure_id)

    (
        group_children_sets,
        group_first_child,
        root_order,
        required,
        pv1_idx,
    ) = _compute_structure_requirements(structure_xsd_path, structure_id)

    root = _build_message_xml_tree(
        hl7_msg,
        structure_id,
        element_to_type,
        type_children,
        type_base,
        element_max_occurs,
        segment_sequences,
        group_children_sets,
        group_first_child,
        root_order,
        required,
        pv1_idx,
    )

    return tostring(root, encoding="unicode")


def convert_er7_to_xml(er7_message: str) -> str:
    """
    Convert ER7 message to XML without using XSD schema.

    This function performs a basic conversion from ER7 to HL7v2 XML format
    without schema validation or structure requirements.

    Args:
        er7_message: The HL7 message in ER7 format

    Returns:
        The HL7v2 XML string representation of the message

    Raises:
        ValueError: If the message cannot be parsed or structure cannot be determined
    """
    return er7_to_hl7v2xml(er7_message, structure_xsd_path=None)


def _extract_text_from_element(elem: XElem) -> str:
    """Extract text content from an XML element, handling nested components."""
    text = elem.text
    if text:
        text = text.strip()
        if text:
            return text

    children_texts: list[str] = []
    append = children_texts.append
    for child in elem:
        child_text = _extract_text_from_element(child)
        if child_text:
            append(child_text)

    if children_texts:
        return "^".join(children_texts)
    return ""


def _strip_namespace(tag: str) -> str:
    """Strip XML namespace prefix from tag name."""
    if tag.startswith("{"):
        idx = tag.find("}")
        if idx != -1:
            return tag[idx + 1 :]
    return tag


def _process_segment_element(seg_elem: XElem, seg_name: str) -> str:
    """
    Convert a segment XML element to ER7 format.

    Args:
        seg_elem: XML element representing an HL7 segment
        seg_name: Name of the segment (e.g., "MSH", "PID")

    Returns:
        ER7-formatted segment string (pipe-delimited fields)
    """
    fields: Dict[int, List[str]] = {}
    max_field = 0

    for field_elem in seg_elem:
        field_tag = field_elem.tag
        if field_tag.startswith("{"):
            idx = field_tag.find("}")
            if idx != -1:
                field_name = field_tag[idx + 1 :]
            else:
                continue
        else:
            field_name = field_tag

        dot_idx = field_name.find(".")
        if dot_idx == -1:
            continue

        try:
            field_num = int(field_name[dot_idx + 1 :])
            if field_num > max_field:
                max_field = field_num
            field_text = _extract_text_from_element(field_elem)
            if field_text:
                if field_num not in fields:
                    fields[field_num] = []
                fields[field_num].append(field_text)
        except (ValueError, IndexError):
            continue

    if max_field == 0:
        return seg_name + "|"

    # MSH segment starts at field 2 (field 1 is the field separator, not in XML)
    start_field = MSH_FIELD_SEPARATOR_INDEX if seg_name == MSH_SEGMENT else 1
    field_parts: List[str] = [""] * (max_field - start_field + 1)

    for i in range(start_field, max_field + 1):
        if i in fields:
            field_parts[i - start_field] = "~".join(fields[i])

    return seg_name + "|" + "|".join(field_parts)


def _is_segment_tag(tag: str) -> bool:
    """Check if tag represents a segment (MSH or 3-letter segment code)."""
    return tag.startswith("MSH") or (len(tag) == 3 and tag.isalpha())


def _process_group_element(group_elem: XElem) -> List[str]:
    """Process a group element and return list of segment ER7 strings."""
    segments: List[str] = []

    for child in group_elem:
        tag = _strip_namespace(child.tag)

        if _is_segment_tag(tag):
            segments.append(_process_segment_element(child, tag))
        else:
            segments.extend(_process_group_element(child))

    return segments


def xml_to_er7(xml_string: str) -> str:
    """
    Convert HL7v2 XML format back to ER7 format.

    This function converts an HL7v2 XML message back to ER7 (pipe-delimited) format.
    The XML should be in the standard HL7v2 XML namespace format.

    Args:
        xml_string: The HL7 message in HL7v2 XML format

    Returns:
        The HL7 message in ER7 format (pipe-delimited, CR-separated)

    Raises:
        ValueError: If the XML cannot be parsed or is invalid
    """
    try:
        root = fromstring(xml_string)
    except Exception as e:
        raise ValueError(f"Failed to parse XML: {e}") from e

    segments: List[str] = []

    for child in root:
        tag = _strip_namespace(child.tag)

        if _is_segment_tag(tag):
            segments.append(_process_segment_element(child, tag))
        else:
            segments.extend(_process_group_element(child))

    return "\r".join(segments)
