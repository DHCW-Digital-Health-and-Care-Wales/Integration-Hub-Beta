"""HL7 ER7 codec - preserves the existing (pre-refactor) HL7 wire format behaviour.

This is the default codec used by BaseTransformer so that all existing HL7
transformers (PHW, Chemo, PIMS, WDS, Core Reference) continue to behave
exactly as before this refactor, with no code changes required on their part.
"""
from __future__ import annotations

import logging

from hl7apy.core import Message
from hl7apy.parser import parse_message

from .base_codec import MessageCodec

logger = logging.getLogger(__name__)


class Hl7Er7Codec(MessageCodec[Message, Message]):
    """Parses/serialises HL7v2 ER7 (pipe-delimited) messages."""

    def parse(self, message_body: str) -> Message:
        hl7_msg = parse_message(message_body)
        logger.debug(f"Message ID: {hl7_msg.msh.msh_10.value}")
        return hl7_msg

    def serialise(self, transformed_message: Message) -> str:
        return transformed_message.to_er7()
