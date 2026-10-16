"""Wire-format codec interface for transformers.

A MessageCodec decouples "how the raw message body is parsed/serialised"
from "how the message is transformed" (BaseTransformer.transform_message).
This allows BaseTransformer/process_message to support any wire format
(HL7 ER7, FHIR JSON, plain XML, etc.) without transformer-specific
branching in the shared processing pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


class MessageCodec(ABC, Generic[TIn, TOut]):
    """Converts between a raw message body string and a transformer's internal types."""

    @abstractmethod
    def parse(self, message_body: str) -> TIn:
        """Parse the raw inbound message body into the transformer's input type."""

    @abstractmethod
    def serialise(self, transformed_message: TOut) -> str:
        """Serialise the transformer's output object back into a wire-format string."""
