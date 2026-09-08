"""Greedy recursive-descent matcher: flat ER7 segment list -> nested grammar-shaped layout.

This replaces the single "current group" pointer approach in ``hl7_validation.convert``
(``_update_group_context`` / ``_build_message_xml_tree``) that can only track one level of group
nesting (design report section 3.2/4.2). Here the call stack *is* the group stack, so nesting depth is
unbounded for free - directly mirroring ``ForTesting/hl7-rust-main``'s ``hl7-2::structure::group()``.

The match is greedy and all-or-nothing: if a required item never matches, or segments are left over
once the grammar is exhausted, the whole match fails (returns None) rather than falling back to a
flat/best-effort rendering - the caller (``converter.er7_to_xml``) turns that into a loud
``MessageNotProcessableError`` (design report section 5.2, point 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple, Union

from .xsd_structure import GroupItem, Occurs, SegmentItem


@dataclass
class MatchedSegment:
    name: str
    segment: Any  # the underlying hl7apy segment object


@dataclass
class MatchedGroup:
    name: str
    items: List[Union[MatchedSegment, "MatchedGroup"]]


def _allows_repetition(max_occurs: Occurs) -> bool:
    return max_occurs == "unbounded" or (isinstance(max_occurs, int) and max_occurs > 1)


def _match_items(
    items: Tuple[Union[SegmentItem, GroupItem], ...],
    segment_tags: List[str],
    segments: List[Any],
    pos: int,
) -> Tuple[Optional[List[Union[MatchedSegment, MatchedGroup]]], int]:
    matched: List[Union[MatchedSegment, MatchedGroup]] = []

    for item in items:
        match_count = 0
        while True:
            if isinstance(item, SegmentItem):
                if pos < len(segment_tags) and segment_tags[pos] == item.name:
                    matched.append(MatchedSegment(item.name, segments[pos]))
                    pos += 1
                    match_count += 1
                    if _allows_repetition(item.max_occurs):
                        continue
                break
            else:
                sub_matched, new_pos = _match_items(item.items, segment_tags, segments, pos)
                if sub_matched is None or new_pos == pos:
                    break
                matched.append(MatchedGroup(item.name, sub_matched))
                pos = new_pos
                match_count += 1
                if _allows_repetition(item.max_occurs):
                    continue
                break

        if match_count == 0 and item.min_occurs >= 1:
            return None, pos

    return matched, pos


def match_structure(root: GroupItem, segment_tags: List[str], segments: List[Any]) -> Optional[MatchedGroup]:
    """Match ``segment_tags``/``segments`` (same order, same length) against ``root``.

    Returns the matched layout tree, or None if the message doesn't fit the grammar (a required item
    never matched, or segments were left unconsumed at the end).
    """
    matched_items, end_pos = _match_items(root.items, segment_tags, segments, 0)
    if matched_items is None or end_pos != len(segment_tags):
        return None
    return MatchedGroup(root.name, matched_items)
