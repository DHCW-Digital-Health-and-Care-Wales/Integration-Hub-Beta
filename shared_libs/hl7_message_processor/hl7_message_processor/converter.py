"""ER7 <-> HL7 v2 XML conversion.

``er7_to_xml`` requires a resolved structure XSD and never runs in a "no schema" mode - the design
report (section 3.1) confirms that a schema-less conversion is exactly what produces flat, non-grouped,
non-decomposed XML (the "missing ADT_A39.PATIENT wrapper" symptom); the fix is to always resolve the
schema first (see ``schema_resolver``/``processor``), not to make the schema-less path smarter.

``xml_to_er7`` needs no schema at all - it recurses into any element whose tag contains "." (a group),
treating everything else as a segment leaf (design report section 4.3/5.3).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element as XElem  # nosec B405

from defusedxml.ElementTree import fromstring, tostring

from .constants import HL7_XML_NAMESPACE, MSH_FIELD_SEPARATOR_INDEX, MSH_SEGMENT, VARIABLE_DATATYPE_FIELDS
from .escaping import decode_hl7_escapes, encode_hl7_escapes
from .exceptions import MessageNotProcessableError
from .matcher import MatchedGroup, MatchedSegment, match_structure
from .message_fields import get_structure_id, parse_er7_message
from .xsd_structure import Occurs, TypeMaps, load_structure_grammar, load_type_maps

logger = logging.getLogger(__name__)

# Matches the (single, self-generated) namespace-prefix declaration ElementTree emits for our one HL7
# v2 XML namespace, e.g. xmlns:ns0="urn:hl7-org:v2xml" (the auto-generated prefix is deterministically
# "ns0" here since the whole document only ever uses this one namespace URI, but it is discovered
# rather than hard-coded for safety).
_NS_DECLARATION_PATTERN = re.compile(r'xmlns:([\w.-]+)="' + re.escape(HL7_XML_NAMESPACE) + r'"')


def _qname(tag: str) -> str:
    return f"{{{HL7_XML_NAMESPACE}}}{tag}"


def _allows_repetition(max_occurs: Occurs) -> bool:
    return max_occurs == "unbounded" or (isinstance(max_occurs, int) and max_occurs > 1)


def _get_field_text(field: Any) -> str:
    try:
        return field.to_er7().strip()
    except Exception:  # noqa: BLE001 - hl7apy field objects can raise a variety of internal errors
        value = getattr(field, "value", None)
        return (value or "").strip()


def _resolve_type_children(type_name: Optional[str], type_maps: TypeMaps) -> List[str]:
    if not type_name:
        return []
    seen = set()
    current: Optional[str] = type_name
    while current is not None and current not in seen:
        seen.add(current)
        children = type_maps.type_children.get(current)
        if children:
            return children
        current = type_maps.type_base.get(current)
    return []


def _emit_element(
    parent: XElem,
    element_name: str,
    raw_value: str,
    type_maps: TypeMaps,
    separator: str = "^",
    type_name_override: Optional[str] = None,
) -> None:
    """Emit ``element_name`` under ``parent``, decomposing ``raw_value`` by ``separator`` if the
    element's type is composite.

    ``separator`` is depth-dependent, per the HL7 v2 encoding rules: a field's own components are
    always "^"-separated (the default, used for the first/outermost decomposition), but if one of
    those components is itself composite (e.g. XCN.9's HD type, decomposing into HD.1/HD.2/HD.3),
    HL7 always uses "&" (the subcomponent separator) for that - and any further - nesting, never
    "^" again. Splitting always happens on the still-raw (not yet escape-decoded) text, so a
    genuine structural "&"/"^" is never confused with an escaped literal ampersand/caret
    (``\\T\\``/``\\S\\``) - those remain literal backslash-letter-backslash sequences until
    ``decode_hl7_escapes`` runs at the leaf, below.

    ``type_name_override`` bypasses ``type_maps.element_to_type`` for fields whose real HL7 data
    type is only known at runtime, from a sibling field's value (see
    ``VARIABLE_DATATYPE_FIELDS`` / ``_emit_segment``), e.g. OBX-5's structure depends on OBX-2.
    """
    elem = XElem(_qname(element_name))
    parent.append(elem)

    type_name = type_name_override or type_maps.element_to_type.get(element_name)
    children = _resolve_type_children(type_name, type_maps)
    if not children:
        if raw_value:
            # MSH.2 (encoding characters, e.g. "^~\&") is the literal delimiter set itself and must
            # never be treated as escaped data - callers route it here unsplit (see _emit_field).
            if element_name == f"{MSH_SEGMENT}.{MSH_FIELD_SEPARATOR_INDEX}":
                elem.text = raw_value
            else:
                elem.text = decode_hl7_escapes(raw_value)
        return

    # HL7 encoding rule: trailing components that were never provided may be OMITTED entirely (not
    # sent as empty) *if* the schema marks them optional (minOccurs=0). Padding every remaining type
    # child with an empty element regardless of that breaks XSD types that don't accept an empty
    # string (e.g. XTN.5-8, numeric country/area/local/extension codes: "invalid value '' for
    # xs:decimal" when a phone number field only supplies its first few components). But some
    # schemas mark composite children as mandatory (minOccurs=1, e.g. HD.1/HD.2) even though HL7's
    # wire format lets them be blank/absent - those must still be emitted (empty) to satisfy the
    # schema's structure, so only skip a missing trailing component when it's genuinely optional.
    components = raw_value.split(separator) if raw_value else []
    for idx, child_name in enumerate(children):
        if idx < len(components):
            _emit_element(elem, child_name, components[idx], type_maps, separator="&")
        elif type_maps.element_min_occurs.get(child_name, 1) >= 1:
            _emit_element(elem, child_name, "", type_maps, separator="&")


def _emit_field(
    parent: XElem,
    segment_name: str,
    field_number: int,
    raw_value: str,
    type_maps: TypeMaps,
    type_name_override: Optional[str] = None,
) -> None:
    field_element_name = f"{segment_name}.{field_number}"

    if segment_name == MSH_SEGMENT and field_number == MSH_FIELD_SEPARATOR_INDEX:
        # MSH.2 (encoding characters) never repeats, even if it happened to contain "~".
        _emit_element(parent, field_element_name, raw_value, type_maps, type_name_override=type_name_override)
        return

    max_occurs = type_maps.element_max_occurs.get(field_element_name, 1)
    reps = (
        raw_value.split("~")
        if raw_value and "~" in raw_value and _allows_repetition(max_occurs)
        else [raw_value or ""]
    )
    for rep in reps:
        _emit_element(parent, field_element_name, rep, type_maps, type_name_override=type_name_override)


def _extract_field_data(segment: Any) -> Dict[int, str]:
    field_map: Dict[int, List[str]] = defaultdict(list)
    for child in segment.children:
        try:
            child_name = str(child.name)
            if "_" in child_name:
                field_index = int(child_name.split("_")[1])
                field_map[field_index].append(_get_field_text(child))
        except (ValueError, IndexError):
            continue
    return {idx: "~".join(values) for idx, values in field_map.items()}


def _resolve_variable_datatype_override(seg_tag: str, field_number: int, field_data: Dict[int, str]) -> Optional[str]:
    """Resolve the HL7 datatype code that should be used to render a variable-typed field.

    Some fields (e.g. OBX-5) have no fixed data type in the schema; their structure depends on the
    value of another field in the same segment (e.g. OBX-2) - see ``VARIABLE_DATATYPE_FIELDS``.

    Returns:
        The datatype code to use instead of the schema-derived type, or ``None`` if the field isn't
        variable-typed or the controlling field has no usable value (callers then fall back to the
        schema-derived type, i.e. plain text for OBX-5).
    """
    value_type_field = VARIABLE_DATATYPE_FIELDS.get((seg_tag, field_number))
    if value_type_field is None:
        return None
    datatype_code = field_data.get(value_type_field, "").strip()
    return datatype_code or None


def _emit_segment(parent: XElem, seg_tag: str, segment: Any, type_maps: TypeMaps) -> None:
    seg_node = XElem(_qname(seg_tag))
    parent.append(seg_node)

    field_data = _extract_field_data(segment)
    sequence_items = type_maps.segment_sequences.get(seg_tag, [])

    if sequence_items:
        for field_num, min_occurs, _max_occurs in sequence_items:
            value = field_data.get(field_num, "")
            type_name_override = _resolve_variable_datatype_override(seg_tag, field_num, field_data)
            if value:
                _emit_field(seg_node, seg_tag, field_num, value, type_maps, type_name_override)
            else:
                for _ in range(min_occurs):
                    _emit_field(seg_node, seg_tag, field_num, "", type_maps, type_name_override)
    else:
        for field_num in sorted(field_data.keys()):
            value = field_data[field_num]
            if value:
                type_name_override = _resolve_variable_datatype_override(seg_tag, field_num, field_data)
                _emit_field(seg_node, seg_tag, field_num, value, type_maps, type_name_override)


def _render_matched(node: Any, parent: XElem, type_maps: TypeMaps) -> None:
    if isinstance(node, MatchedSegment):
        _emit_segment(parent, node.name, node.segment, type_maps)
    else:
        assert isinstance(node, MatchedGroup)
        group_node = XElem(_qname(node.name))
        parent.append(group_node)
        for child in node.items:
            _render_matched(child, group_node, type_maps)


def er7_to_xml(
    er7_message: str,
    structure_xsd_path: str,
    structure_id: Optional[str] = None,
    parsed_message: Optional[Any] = None,
) -> str:
    """Convert an ER7 message to HL7 v2 XML, using ``structure_xsd_path`` to decide field
    decomposition, repetition, and (arbitrary-depth) group nesting.

    Args:
        er7_message: The HL7 message in ER7 format.
        structure_xsd_path: Path to the resolved structure XSD (see ``schema_resolver``). Required -
            this function never runs in a schema-less mode (see module docstring).
        structure_id: The message structure (e.g. "ADT_A05"), if already known; otherwise read from
            MSH-9.3 of the parsed message.
        parsed_message: An already-parsed hl7apy message, to avoid parsing ``er7_message`` twice.

    Raises:
        MessageNotProcessableError: if the structure can't be determined, or the message's segments
            don't fit the resolved schema's grammar.
    """
    hl7_msg = parsed_message if parsed_message is not None else parse_er7_message(er7_message)

    resolved_structure_id = structure_id or get_structure_id(hl7_msg)
    if not resolved_structure_id:
        raise MessageNotProcessableError("Unable to determine message structure (MSH-9.3) from ER7 message")

    grammar = load_structure_grammar(structure_xsd_path, resolved_structure_id)
    type_maps = load_type_maps(structure_xsd_path)

    segments = list(hl7_msg.children)
    segment_tags = [str(segment.name) for segment in segments]

    matched = match_structure(grammar, segment_tags, segments)
    if matched is None:
        logger.error(
            "Message with structure '%s' does not fit the resolved schema's grammar; not processable",
            resolved_structure_id,
        )
        raise MessageNotProcessableError(
            f"Message segments do not fit the grammar for structure '{resolved_structure_id}'"
        )

    root = XElem(_qname(matched.name))
    for child in matched.items:
        _render_matched(child, root, type_maps)

    return _serialize_with_default_namespace(root)


def _serialize_with_default_namespace(root: XElem) -> str:
    """Serialize ``root`` with the HL7 v2 XML namespace as the *default* namespace
    (``xmlns="urn:hl7-org:v2xml"``) rather than a prefixed one (``xmlns:ns0="..."`` / ``<ns0:TAG>``) -
    WRRS cannot process prefixed messages.

    ElementTree has no built-in way to serialize a namespace as default without
    ``register_namespace``, which is a **process-wide** registration (shared with every other module
    in the process using ``xml.etree.ElementTree``, including unrelated packages like
    ``hl7_validation`` that also serialize this same namespace URI with their own conventions) - so it
    is deliberately not used here. Instead, the auto-generated prefix is rewritten on the serialized
    string only, scoped to this one call: only tag-name occurrences (immediately after ``<`` or
    ``</``) are rewritten, never arbitrary text/attribute content, so real field data containing a
    coincidental "ns0:" substring is never touched.
    """
    xml_string = str(tostring(root, encoding="unicode"))
    match = _NS_DECLARATION_PATTERN.search(xml_string)
    if match is None:
        return xml_string

    prefix = match.group(1)
    xml_string = xml_string.replace(f'xmlns:{prefix}="{HL7_XML_NAMESPACE}"', f'xmlns="{HL7_XML_NAMESPACE}"', 1)
    return re.sub(rf"<(/?){re.escape(prefix)}:", r"<\1", xml_string)


def _strip_namespace(tag: str) -> str:
    if tag.startswith("{"):
        idx = tag.find("}")
        if idx != -1:
            return tag[idx + 1 :]
    return tag


def _extract_text_from_element(elem: XElem, separator: str = "^") -> str:
    """Extract ER7 text from ``elem``, re-joining composite children with ``separator`` if ``elem``
    itself has no direct text (i.e. it's a composite element whose value lives in its children).

    ``separator`` is depth-dependent, mirroring ``_emit_element``: the top-level call (one field
    element, e.g. an XCN field) joins its immediate components with "^" (the default); if one of
    those components is itself composite (e.g. XCN.9/HD decomposing into HD.1/HD.2/HD.3), that -
    and any deeper - nesting is always joined with "&" (the subcomponent separator), never "^"
    again, per the HL7 v2 encoding rules. Each leaf's text is escaped via ``encode_hl7_escapes``
    before any joining happens, so a literal "&"/"^" in the original data (already turned into a
    literal char by the XML parser) is turned back into ``\\T\\``/``\\S\\`` before it could ever
    be confused with a separator this function itself adds.
    """
    text = elem.text.strip() if elem.text else ""
    if text:
        return encode_hl7_escapes(text)
    children_texts = [_extract_text_from_element(child, separator="&") for child in elem]
    children_texts = [text for text in children_texts if text]
    return separator.join(children_texts) if children_texts else ""


def _process_segment_element(seg_elem: XElem, seg_name: str) -> str:
    fields: Dict[int, List[str]] = {}
    max_field = 0

    for field_elem in seg_elem:
        field_tag = _strip_namespace(field_elem.tag)
        dot_idx = field_tag.find(".")
        if dot_idx == -1:
            continue
        try:
            field_num = int(field_tag[dot_idx + 1 :])
        except ValueError:
            continue
        max_field = max(max_field, field_num)
        if seg_name == MSH_SEGMENT and field_num == MSH_FIELD_SEPARATOR_INDEX:
            # MSH.2 holds the literal encoding characters (e.g. "^~\&") - never escape/encode it.
            text = (field_elem.text or "").strip()
        else:
            text = _extract_text_from_element(field_elem)
        if text:
            fields.setdefault(field_num, []).append(text)

    if max_field == 0:
        return seg_name + "|"

    # MSH starts at field 2 (field 1, the field separator, isn't represented in the XML).
    start_field = MSH_FIELD_SEPARATOR_INDEX if seg_name == MSH_SEGMENT else 1
    parts: List[str] = [""] * (max_field - start_field + 1)
    for field_num in range(start_field, max_field + 1):
        if field_num in fields:
            parts[field_num - start_field] = "~".join(fields[field_num])

    return seg_name + "|" + "|".join(parts)


def _process_group_element(group_elem: XElem) -> List[str]:
    segments: List[str] = []
    for child in group_elem:
        tag = _strip_namespace(child.tag)
        if "." in tag:
            segments.extend(_process_group_element(child))
        else:
            segments.append(_process_segment_element(child, tag))
    return segments


def xml_to_er7(xml_string: str) -> str:
    """Convert HL7 v2 XML back to ER7. No schema is required (see module docstring)."""
    root = fromstring(xml_string)
    segments = _process_group_element(root)
    return "\r".join(segments)
