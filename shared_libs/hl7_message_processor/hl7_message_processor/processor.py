"""High-level orchestration: resolve (version, structure) from a raw ER7 message, then convert.

This is the entry point that guarantees the "resolve schema before conversion, unconditionally" rule
from the design report (section 3.1/5.1): ``converter.er7_to_xml`` always requires an already-resolved
XSD path, and this module is what resolves it from MSH-12.1/MSH-9 before ever calling it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .converter import er7_to_xml
from .exceptions import MessageNotProcessableError, SchemaNotFoundError
from .message_fields import get_message_code, get_structure_id, get_trigger_event, get_version, parse_er7_message
from .schema_resolver import SchemaResolver, resolve_schema_path
from .trigger_structure_map import resolve_structure_from_trigger

logger = logging.getLogger(__name__)


@dataclass
class ProcessedMessage:
    xml: str
    structure_id: str
    version: str
    xsd_path: Path


def _resolve_structure_id(msg: Any) -> str:
    structure_id = get_structure_id(msg)
    if structure_id:
        return structure_id

    message_code = get_message_code(msg)
    trigger_event = get_trigger_event(msg)
    if message_code and trigger_event:
        aliased_structure_id = resolve_structure_from_trigger(message_code, trigger_event)
        if aliased_structure_id:
            return aliased_structure_id

    logger.error(
        "Unable to resolve message structure: MSH-9.3 absent and (MSH-9.1, MSH-9.2) = (%r, %r) has no "
        "known alias in the trigger->structure table",
        message_code,
        trigger_event,
    )
    raise MessageNotProcessableError(
        "Unable to determine message structure: MSH-9.3 is absent and MSH-9.1/MSH-9.2 do not resolve "
        "to a known structure"
    )


def process_er7(er7_message: str, resolver: Optional[SchemaResolver] = None) -> ProcessedMessage:
    """Resolve the schema for ``er7_message`` (from MSH-12.1 + MSH-9) and convert it to HL7 v2 XML.

    Raises:
        MessageNotProcessableError: if the version/structure can't be determined, no schema can be
            resolved for them, or the message doesn't fit the resolved schema's grammar. Every failure
            is logged as an error before being raised (confirmed decision, design report section 7.3) -
            there is no flat/best-effort fallback.
    """
    msg = parse_er7_message(er7_message)

    version = get_version(msg)
    if not version:
        logger.error("Unable to resolve HL7 version: MSH-12.1 is absent")
        raise MessageNotProcessableError("Unable to determine HL7 version: MSH-12.1 is absent")

    structure_id = _resolve_structure_id(msg)

    try:
        xsd_path = resolve_schema_path(version, structure_id, resolver=resolver)
    except SchemaNotFoundError as error:
        logger.error("Message not processable: %s", error)
        raise MessageNotProcessableError(str(error)) from error

    xml = er7_to_xml(er7_message, str(xsd_path), structure_id=structure_id, parsed_message=msg)

    return ProcessedMessage(xml=xml, structure_id=structure_id, version=version, xsd_path=xsd_path)
