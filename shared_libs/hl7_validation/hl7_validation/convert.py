from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from hl7apy.parser import parse_message


def _set_text_if_not_none(node: Element, value: Any) -> None:
    if value is not None:
        node.text = str(value)


def _get_field_text(field: Any) -> str:
    text_value: str | None = None
    try:
        text_value = field.to_er7()  # type: ignore[attr-defined]
    except Exception:
        text_value = getattr(field, "value", None)
    return (text_value or "").strip()


def er7_to_xml(er7_message: str) -> str:
    hl7_msg = parse_message(er7_message)

    root = Element("HL7Message")
    for segment in hl7_msg.children:
        seg_tag = segment.name
        seg_node = SubElement(root, seg_tag)

        if seg_tag == "MSH":
            # Emit all MSH fields (1..21) to ensure presence for validation.
            max_fields = 21
            field_number_to_child: dict[int, Any] = {}
            for child in segment.children:
                try:
                    number = int(str(child.name).split("_")[1])
                    field_number_to_child[number] = child
                except Exception:
                    continue
            for field_index in range(1, max_fields + 1):
                text_value = ""
                field = field_number_to_child.get(field_index)
                if field is not None:
                    text_value = _get_field_text(field)

                field_tag = f"{seg_tag}.{field_index}"
                field_node = SubElement(seg_node, field_tag)
                if text_value:
                    _set_text_if_not_none(field_node, text_value)
            continue

        if seg_tag == "PID":
            indices = [3, 5, 7, 8, 29]
            pid_field_number_to_children: dict[int, list[Any]] = {}
            for child in segment.children:
                try:
                    number = int(str(child.name).split("_")[1])
                    pid_field_number_to_children.setdefault(number, []).append(child)
                except Exception:
                    continue
            for field_index in indices:
                children = pid_field_number_to_children.get(field_index, [])
                if not children:
                    continue
                if field_index == 3:
                    for child in children:
                        text_value = _get_field_text(child)
                        if text_value:
                            SubElement(seg_node, f"{seg_tag}.3").text = text_value
                else:
                    for child in children:
                        text_value = _get_field_text(child)
                        if text_value:
                            SubElement(
                                seg_node, f"{seg_tag}.{field_index}"
                            ).text = text_value
                            break
            continue

        for child in segment.children:
            text_value = _get_field_text(child)
            if not text_value:
                continue
            try:
                number = int(str(child.name).split("_")[1])
            except Exception:
                continue
            field_tag = f"{seg_tag}.{number}"
            field_node = SubElement(seg_node, field_tag)
            _set_text_if_not_none(field_node, text_value)

    return tostring(root, encoding="unicode")
