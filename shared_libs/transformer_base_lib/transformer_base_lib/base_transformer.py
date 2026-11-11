from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from hl7apy.core import Message
from hl7apy.parser import parse_message


class BaseTransformer(ABC):
    """Abstract base class for message transformers.

    Provides a standardised interface for creating message transformers. HL7 transformers use the default
    wire-format hooks (parse_input / serialise_output); transformers for other payloads, such as XML to FHIR,
    override those two hooks.
    """

    def __init__(self, transformer_name: str, config_path: Optional[str] = None):
        self.transformer_name = transformer_name
        self.config_path = config_path or self._get_default_config_path()

    def parse_input(self, message_body: str) -> Any:
        """Parse the inbound message body. Defaults to an HL7 v2 (ER7) parse."""
        return parse_message(message_body)

    @abstractmethod
    def transform_message(self, hl7_msg: Any) -> Any:
        pass

    def serialise_output(self, transformed_message: Any) -> str:
        """Serialise the transformed message for the egress queue. Defaults to HL7 v2 (ER7) text."""
        return transformed_message.to_er7()  # type: ignore[no-any-return]

    def get_egress_properties(
        self, incoming_props: Optional[Dict[str, str]], transformed_msg: Any
    ) -> Optional[Dict[str, str]]:
        """Service Bus application properties for the outgoing message. Defaults to passing them through unchanged."""
        return incoming_props

    def get_received_audit_text(self) -> str:
        return f"Message received for {self.transformer_name} transformation"

    def get_processed_audit_text(self, hl7_msg: Message) -> str:
        sending_app = self._get_sending_app(hl7_msg)
        return f"{self.transformer_name} transformation applied for SENDING_APP: {sending_app}"

    def _get_sending_app(self, hl7_msg: Message) -> str:
        try:
            return hl7_msg.msh.msh_3.msh_3_1.value
        except (AttributeError, IndexError):
            return "UNKNOWN"

    def _get_default_config_path(self) -> str:
        # Note this resolves within the transformer_base_lib package and not the specific transformer implementation!
        return os.path.join(os.path.dirname(__file__), "config.ini")

    def run(self) -> None:
        from .run_transformer import run_transformer_app  # noqa: PLC0415

        run_transformer_app(self)
