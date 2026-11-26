"""Parse HL7 v2.x, XML, and JSON messages into a structure tree with exact character offsets."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from xml.parsers import expat

from ultra7.formats.hl7_dictionary import describe_hl7
from ultra7.models import MessageFormat

_MAX_PREVIEW_LEN = 60


@dataclass(frozen=True)
class StructureNode:
    """A node in the message structure tree, mapped to exact character offsets in the source text."""

    label: str
    value: str
    start: int
    end: int
    children: tuple[StructureNode, ...] = ()
    description: str = ""
    path: str = ""
    value_start: int | None = None
    value_end: int | None = None

    @property
    def display_label(self) -> str:
        if self.description:
            return f"{self.label} · {self.description}"
        return self.label

    @property
    def editable(self) -> bool:
        return self.value_start is not None and self.value_end is not None


def _preview(text: str) -> str:
    single = " ".join(text.split())
    if len(single) <= _MAX_PREVIEW_LEN:
        return single
    return single[: _MAX_PREVIEW_LEN - 1] + "…"


def parse_structure(content: str, message_format: MessageFormat) -> tuple[list[StructureNode], str | None]:
    """Parse *content* according to *message_format*.

    Returns ``(nodes, error_message)``. When parsing fails (e.g. malformed XML/JSON
    mid-edit), ``nodes`` is empty and ``error_message`` describes the parse error.
    """
    if not content.strip():
        return [], None
    if message_format == "hl7":
        return parse_hl7_structure(content), None
    if message_format == "xml":
        return parse_xml_structure(content)
    if message_format == "json":
        return parse_json_structure(content)
    return [], f"Structure view is not supported for '{message_format}'"


# ---------------------------------------------------------------------------
# HL7 v2.x ER7 parser
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(r"[^\r\n]+")


def _split_with_offsets(text: str, sep: str, base_offset: int) -> list[tuple[str, int, int]]:
    parts: list[tuple[str, int, int]] = []
    pos = 0
    while True:
        idx = text.find(sep, pos)
        if idx == -1:
            parts.append((text[pos:], base_offset + pos, base_offset + len(text)))
            break
        parts.append((text[pos:idx], base_offset + pos, base_offset + idx))
        pos = idx + len(sep)
    return parts


def _build_component_nodes(
    text: str,
    prefix: str,
    base_offset: int,
    comp_sep: str,
    subcomp_sep: str,
) -> tuple[StructureNode, ...]:
    if comp_sep not in text:
        return ()
    nodes: list[StructureNode] = []
    for comp_idx, (comp_val, comp_start, comp_end) in enumerate(
        _split_with_offsets(text, comp_sep, base_offset), start=1
    ):
        if not comp_val:
            continue
        comp_label = f"{prefix}.{comp_idx}"
        sub_nodes: list[StructureNode] = []
        if subcomp_sep in comp_val:
            for sub_idx, (sub_val, sub_start, sub_end) in enumerate(
                _split_with_offsets(comp_val, subcomp_sep, comp_start), start=1
            ):
                if not sub_val:
                    continue
                sub_nodes.append(
                    StructureNode(
                        label=f"{comp_label}.{sub_idx}",
                        value=_preview(sub_val),
                        start=sub_start,
                        end=sub_end,
                        description=describe_hl7(f"{comp_label}.{sub_idx}"),
                        path=f"{comp_label}.{sub_idx}",
                        value_start=sub_start,
                        value_end=sub_end,
                    )
                )
        nodes.append(
            StructureNode(
                label=comp_label,
                value=_preview(comp_val),
                start=comp_start,
                end=comp_end,
                children=tuple(sub_nodes),
                description=describe_hl7(comp_label),
                path=comp_label,
                value_start=None if sub_nodes else comp_start,
                value_end=None if sub_nodes else comp_end,
            )
        )
    return tuple(nodes)


def parse_hl7_structure(content: str) -> list[StructureNode]:
    """Parse HL7 v2.x ER7 segments, fields, repetitions, components, and subcomponents."""
    field_sep = "|"
    comp_sep = "^"
    rep_sep = "~"
    subcomp_sep = "&"

    # Sniff encoding characters from MSH if present.
    for match in _LINE_RE.finditer(content):
        line = match.group(0)
        if line.startswith("MSH") and len(line) >= 8:
            field_sep = line[3]
            comp_sep = line[4]
            rep_sep = line[5]
            subcomp_sep = line[7]
            break

    segments: list[StructureNode] = []
    for match in _LINE_RE.finditer(content):
        line = match.group(0)
        line_start = match.start()
        line_end = match.end()
        if not line.strip():
            continue

        parts = _split_with_offsets(line, field_sep, line_start)
        seg_name = parts[0][0].strip() or "SEG"
        is_msh = seg_name == "MSH"

        field_nodes: list[StructureNode] = []
        if is_msh and len(line) > 3 and line[3] == field_sep:
            field_nodes.append(
                StructureNode(
                    label="MSH-1",
                    value=field_sep,
                    start=line_start + 3,
                    end=line_start + 4,
                    description=describe_hl7("MSH-1"),
                    path="MSH-1",
                )
            )

        for idx, (raw_val, f_start, f_end) in enumerate(parts[1:], start=1):
            field_num = idx + 1 if is_msh else idx
            if not raw_val:
                continue
            field_label = f"{seg_name}-{field_num}"

            # MSH-2 holds the encoding characters themselves; do not split them.
            if is_msh and field_num == 2:
                field_nodes.append(
                    StructureNode(
                        label=field_label,
                        value=raw_val,
                        start=f_start,
                        end=f_end,
                        description=describe_hl7(field_label),
                        path=field_label,
                        value_start=f_start,
                        value_end=f_end,
                    )
                )
                continue

            children: tuple[StructureNode, ...]
            if rep_sep in raw_val:
                rep_nodes: list[StructureNode] = []
                for rep_idx, (rep_val, r_start, r_end) in enumerate(
                    _split_with_offsets(raw_val, rep_sep, f_start), start=1
                ):
                    if not rep_val:
                        continue
                    rep_label = f"{field_label}[{rep_idx}]"
                    rep_children = _build_component_nodes(rep_val, rep_label, r_start, comp_sep, subcomp_sep)
                    rep_nodes.append(
                        StructureNode(
                            label=rep_label,
                            value=_preview(rep_val),
                            start=r_start,
                            end=r_end,
                            children=rep_children,
                            description=describe_hl7(rep_label),
                            path=rep_label,
                            value_start=None if rep_children else r_start,
                            value_end=None if rep_children else r_end,
                        )
                    )
                children = tuple(rep_nodes)
            else:
                children = _build_component_nodes(raw_val, field_label, f_start, comp_sep, subcomp_sep)

            field_nodes.append(
                StructureNode(
                    label=field_label,
                    value=_preview(raw_val),
                    start=f_start,
                    end=f_end,
                    children=children,
                    description=describe_hl7(field_label),
                    path=field_label,
                    value_start=None if children else f_start,
                    value_end=None if children else f_end,
                )
            )

        segments.append(
            StructureNode(
                label=seg_name,
                value=_preview(line),
                start=line_start,
                end=line_end,
                children=tuple(field_nodes),
                description=describe_hl7(seg_name),
                path=seg_name,
            )
        )

    return segments


# ---------------------------------------------------------------------------
# XML parser (expat with exact character offsets)
# ---------------------------------------------------------------------------

_ATTR_RE = re.compile(r'([A-Za-z_][\w:.-]*)\s*=\s*("[^"]*"|\'[^\']*\')')


def _build_byte_to_char_map(content: str, raw: bytes) -> list[int] | None:
    """Return a byte-offset -> char-offset table, or None if content is pure ASCII."""
    if len(raw) == len(content):
        return None
    mapping = [0] * (len(raw) + 1)
    byte_pos = 0
    for char_idx, ch in enumerate(content):
        ch_len = len(ch.encode("utf-8"))
        for offset in range(ch_len):
            mapping[byte_pos + offset] = char_idx
        byte_pos += ch_len
    mapping[len(raw)] = len(content)
    return mapping


def parse_xml_structure(content: str) -> tuple[list[StructureNode], str | None]:
    """Parse XML into a StructureNode tree using expat for exact character offsets."""
    raw = content.encode("utf-8")
    byte_to_char = _build_byte_to_char_map(content, raw)

    def _to_char(byte_idx: int) -> int:
        if byte_to_char is None:
            return byte_idx
        return byte_to_char[min(byte_idx, len(raw))]

    # Stack entries: (tag_name, xpath, start_char, open_tag_end, direct_text_chunks, child_nodes)
    stack: list[tuple[str, str, int, int, list[str], list[StructureNode]]] = []
    roots: list[StructureNode] = []

    parser = expat.ParserCreate()

    def _on_start(name: str, _attrs: dict[str, str]) -> None:
        start_char = _to_char(parser.CurrentByteIndex)
        tag_end = content.find(">", start_char)
        parent_xpath = stack[-1][1] if stack else ""
        xpath = f"{parent_xpath}/{name}"
        children: list[StructureNode] = []
        if tag_end != -1:
            tag_slice = content[start_char : tag_end + 1]
            name_end = tag_slice.find(name)
            search_from = (name_end + len(name)) if name_end != -1 else 1
            for attr_match in _ATTR_RE.finditer(tag_slice, search_from):
                attr_name = attr_match.group(1)
                attr_val = attr_match.group(2)[1:-1]
                val_start = start_char + attr_match.start(2) + 1
                val_end = start_char + attr_match.end(2) - 1
                children.append(
                    StructureNode(
                        label=f"@{attr_name}",
                        value=_preview(attr_val),
                        start=start_char + attr_match.start(),
                        end=start_char + attr_match.end(),
                        path=f"{xpath}/@{attr_name}",
                        value_start=val_start,
                        value_end=val_end,
                    )
                )
        stack.append((name, xpath, start_char, tag_end, [], children))

    def _on_char_data(data: str) -> None:
        if stack:
            stack[-1][4].append(data)

    def _on_end(_name: str) -> None:
        if not stack:
            return
        tag_name, xpath, start_char, open_tag_end, text_chunks, children = stack.pop()
        is_self_closing = open_tag_end != -1 and open_tag_end > start_char and content[open_tag_end - 1] == "/"
        has_child_elements = any(c.label.startswith("<") for c in children)
        if is_self_closing:
            end_char = open_tag_end + 1
            v_start: int | None = None
            v_end: int | None = None
        else:
            end_tag_start = _to_char(parser.CurrentByteIndex)
            gt = content.find(">", end_tag_start)
            end_char = (gt + 1) if gt != -1 else len(content)
            if not has_child_elements and open_tag_end != -1 and open_tag_end + 1 <= end_tag_start:
                v_start = open_tag_end + 1
                v_end = end_tag_start
            else:
                v_start = None
                v_end = None
        value = _preview("".join(text_chunks))
        node = StructureNode(
            label=f"<{tag_name}>",
            value=value,
            start=start_char,
            end=end_char,
            children=tuple(children),
            path=xpath,
            value_start=v_start,
            value_end=v_end,
        )
        if stack:
            stack[-1][5].append(node)
        else:
            roots.append(node)

    parser.StartElementHandler = _on_start
    parser.CharacterDataHandler = _on_char_data
    parser.EndElementHandler = _on_end

    try:
        parser.Parse(raw, True)
    except expat.ExpatError as exc:
        return [], f"Invalid XML: {exc}"

    return roots, None


# ---------------------------------------------------------------------------
# JSON parser (exact character offsets)
# ---------------------------------------------------------------------------

_WHITESPACE = " \t\r\n"


def _skip_ws(content: str, pos: int) -> int:
    n = len(content)
    while pos < n and content[pos] in _WHITESPACE:
        pos += 1
    return pos


def parse_json_structure(content: str) -> tuple[list[StructureNode], str | None]:
    """Parse JSON into a StructureNode tree with exact character offsets."""
    decoder = json.JSONDecoder()
    n = len(content)

    def _parse_value(pos: int, label: str, json_path: str) -> tuple[StructureNode, int]:
        pos = _skip_ws(content, pos)
        if pos >= n:
            raise ValueError("Unexpected end of JSON")
        ch = content[pos]
        if ch == "{":
            start = pos
            pos = _skip_ws(content, pos + 1)
            children: list[StructureNode] = []
            if pos < n and content[pos] == "}":
                return StructureNode(label=label, value="{}", start=start, end=pos + 1, path=json_path), pos + 1
            while pos < n:
                pos = _skip_ws(content, pos)
                key_start = pos
                key, pos = decoder.raw_decode(content, pos)
                if not isinstance(key, str):
                    raise ValueError(f"Expected string key at offset {key_start}")
                pos = _skip_ws(content, pos)
                if pos >= n or content[pos] != ":":
                    raise ValueError(f"Expected ':' at offset {pos}")
                child_path = f"{json_path}.{key}"
                child, pos = _parse_value(pos + 1, key, child_path)
                children.append(
                    StructureNode(
                        label=child.label,
                        value=child.value,
                        start=key_start,
                        end=child.end,
                        children=child.children,
                        path=child_path,
                        value_start=child.value_start,
                        value_end=child.value_end,
                    )
                )
                pos = _skip_ws(content, pos)
                if pos < n and content[pos] == ",":
                    pos += 1
                    continue
                if pos < n and content[pos] == "}":
                    return (
                        StructureNode(
                            label=label,
                            value=f"{{{len(children)} keys}}",
                            start=start,
                            end=pos + 1,
                            children=tuple(children),
                            path=json_path,
                        ),
                        pos + 1,
                    )
                raise ValueError(f"Expected ',' or '}}' at offset {pos}")
            raise ValueError("Unterminated object")

        if ch == "[":
            start = pos
            pos = _skip_ws(content, pos + 1)
            children = []
            if pos < n and content[pos] == "]":
                return StructureNode(label=label, value="[]", start=start, end=pos + 1, path=json_path), pos + 1
            index = 0
            while pos < n:
                child, pos = _parse_value(pos, f"[{index}]", f"{json_path}[{index}]")
                children.append(child)
                index += 1
                pos = _skip_ws(content, pos)
                if pos < n and content[pos] == ",":
                    pos += 1
                    continue
                if pos < n and content[pos] == "]":
                    return (
                        StructureNode(
                            label=label,
                            value=f"[{len(children)} items]",
                            start=start,
                            end=pos + 1,
                            children=tuple(children),
                            path=json_path,
                        ),
                        pos + 1,
                    )
                raise ValueError(f"Expected ',' or ']' at offset {pos}")
            raise ValueError("Unterminated array")

        start = pos
        val, end = decoder.raw_decode(content, pos)
        val_str = json.dumps(val) if isinstance(val, (bool, type(None))) else str(val)
        # For JSON strings, edit inside quotes; for scalars (numbers/bools/null), edit the raw token.
        if isinstance(val, str) and end - start >= 2 and content[start] == '"' and content[end - 1] == '"':
            v_start, v_end = start + 1, end - 1
        else:
            v_start, v_end = start, end
        return (
            StructureNode(
                label=label,
                value=_preview(val_str),
                start=start,
                end=end,
                path=json_path,
                value_start=v_start,
                value_end=v_end,
            ),
            end,
        )

    try:
        root, end = _parse_value(0, "root", "$")
        trailing = _skip_ws(content, end)
        if trailing < n:
            raise ValueError(f"Extra data at offset {trailing}")
    except (ValueError, json.JSONDecodeError) as exc:
        return [], f"Invalid JSON: {exc}"

    return [root], None


def filter_structure_nodes(
    nodes: list[StructureNode] | tuple[StructureNode, ...], query: str
) -> list[StructureNode]:
    """Return a pruned copy of *nodes* containing only nodes matching *query* or their ancestors."""
    needle = query.strip().lower()
    if not needle:
        return list(nodes)
    kept: list[StructureNode] = []
    for node in nodes:
        matches_self = (
            needle in node.label.lower()
            or needle in node.description.lower()
            or needle in node.value.lower()
            or needle in node.path.lower()
        )
        filtered_children = filter_structure_nodes(node.children, needle)
        if matches_self or filtered_children:
            kept.append(
                StructureNode(
                    label=node.label,
                    value=node.value,
                    start=node.start,
                    end=node.end,
                    children=tuple(filtered_children) if filtered_children else (node.children if matches_self else ()),
                    description=node.description,
                    path=node.path,
                    value_start=node.value_start,
                    value_end=node.value_end,
                )
            )
    return kept


def find_deepest_node(nodes: list[StructureNode] | tuple[StructureNode, ...], offset: int) -> StructureNode | None:
    """Return the deepest StructureNode covering *offset*, or None if none match."""
    for node in nodes:
        if node.start <= offset <= node.end:
            # Prefer strict containment when adjacent nodes share a boundary,
            # but allow end-boundary match if nothing else contains offset.
            if offset < node.end or node.start == node.end:
                deeper = find_deepest_node(node.children, offset)
                return deeper if deeper is not None else node
    # Second pass: allow inclusive end-boundary match (e.g. cursor right at end of token).
    for node in nodes:
        if node.start <= offset <= node.end:
            deeper = find_deepest_node(node.children, offset)
            return deeper if deeper is not None else node
    return None
