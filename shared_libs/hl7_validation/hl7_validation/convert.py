from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from hl7apy.parser import parse_message


def _set_text_if_not_none(node: Element, value: Any) -> None:
    if value is not None:
        node.text = str(value)


def er7_to_xml(er7_message: str) -> str:
    """
    Convert HL7 ER7 to XML, producing dotted element names (e.g., MSH.7, PID.3.1)
    to align with XSD validation needs.
    """
    hl7_msg = parse_message(er7_message)

    root = Element("HL7Message")
    for segment in hl7_msg.children:
        seg_tag = segment.name
        seg_node = SubElement(root, seg_tag)

        # Special handling to align with minimal schema expectations
        if seg_tag == "MSH":
            total_fields = 12
            for field_index in range(1, total_fields + 1):
                field_tag = f"{seg_tag}.{field_index}"
                field_node = SubElement(seg_node, field_tag)
                if field_index - 1 < len(segment.children):
                    field = segment.children[field_index - 1]
                    text_value = None
                    try:
                        text_value = field.to_er7()  # type: ignore[attr-defined]
                    except Exception:
                        text_value = getattr(field, "value", None)
                    _set_text_if_not_none(field_node, text_value)
            continue

        if seg_tag == "PID":
            indices = [3, 5, 7, 8, 29]
            for field_index in indices:
                field_tag = f"{seg_tag}.{field_index}"
                field_node = SubElement(seg_node, field_tag)
                if field_index - 1 < len(segment.children):
                    field = segment.children[field_index - 1]
                    text_value = None
                    try:
                        text_value = field.to_er7()  # type: ignore[attr-defined]
                    except Exception:
                        text_value = getattr(field, "value", None)
                    _set_text_if_not_none(field_node, text_value)
            continue

        # Default: output all fields present
        for field_index, field in enumerate(segment.children, start=1):
            field_tag = f"{seg_tag}.{field_index}"
            field_node = SubElement(seg_node, field_tag)
            text_value = None
            try:
                text_value = field.to_er7()  # type: ignore[attr-defined]
            except Exception:
                text_value = getattr(field, "value", None)
            _set_text_if_not_none(field_node, text_value)

    return tostring(root, encoding="unicode")


