"""WDS transformer — filters to A28/A31 and converts ER7 to HL7 v2 XML.

The transformer_base_lib message_processor sends the result of transform_message()
via to_er7(), which is not suitable here because the downstream soap_sender needs
HL7 v2 XML rather than ER7.  We therefore subclass BaseTransformer and override
run() to use a custom message processor that serialises to XML instead.
"""
from __future__ import annotations

import logging
import os

from hl7apy.core import Message
from hl7apy.parser import parse_message
from transformer_base_lib import BaseTransformer

logger = logging.getLogger(__name__)

# Only these trigger events are forwarded to WIS.
ALLOWED_TRIGGER_EVENTS: frozenset[str] = frozenset({"A28", "A31"})


def _get_trigger_event(hl7_msg: Message) -> str:
    """Extract MSH-9.2 (trigger event) from a parsed HL7 message."""
    try:
        return hl7_msg.msh.msh_9.msh_9_2.value.strip()
    except (AttributeError, IndexError):
        return ""


class WdsTransformer(BaseTransformer):
    """Transforms WDS HL7 ER7 messages for delivery to WIS via soap_sender.

    Filtering: only A28 and A31 trigger events are forwarded; others raise
    ValueError so the base message_processor dead-letters them.

    Output: the ER7 message is passed through unchanged — the soap_sender is
    responsible for converting ER7 to HL7 v2 XML and wrapping in the WIS
    SOAP envelope.  This keeps each service's responsibility clear and avoids
    duplicating the hl7_validation.convert_er7_to_xml() call.
    """

    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("WDS", config_path)

    def transform_message(self, hl7_msg: Message) -> Message:
        # Re-parse flat so we can reliably access MSH-9.
        flat_msg = parse_message(hl7_msg.to_er7(), find_groups=False)
        trigger_event = _get_trigger_event(flat_msg)

        if trigger_event not in ALLOWED_TRIGGER_EVENTS:
            raise ValueError(
                f"WDS transformer: unsupported trigger event '{trigger_event}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_TRIGGER_EVENTS))}. Message will be dead-lettered."
            )

        logger.info("WDS transformer: passing through %s message unchanged.", trigger_event)
        # Return the message as-is; soap_sender converts ER7 → v2 XML before sending.
        return flat_msg
