from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Optional

from .codecs import Hl7Er7Codec, MessageCodec


class BaseTransformer(ABC):
    """Abstract base class for message transformers.

    Provides a standardised interface for creating message transformers for
    any wire format. The `codec` controls how the raw message body is
    parsed into `transform_message`'s input, and how its output is
    serialised back to a wire string - it defaults to HL7 ER7 so that
    existing HL7 transformers are unaffected unless they opt into a
    different codec (e.g. FhirJsonCodec).
    """

    def __init__(
        self,
        transformer_name: str,
        config_path: Optional[str] = None,
        codec: Optional[MessageCodec] = None,
    ):
        self.transformer_name = transformer_name
        self.config_path = config_path or self._get_default_config_path()
        self.codec: MessageCodec = codec or Hl7Er7Codec()

    @abstractmethod
    def transform_message(self, parsed_message: Any) -> Any:
        pass

    def get_received_audit_text(self) -> str:
        return f"Message received for {self.transformer_name} transformation"

    def get_processed_audit_text(self, hl7_msg: Any) -> str:
        sending_app = self._get_sending_app(hl7_msg)
        return f"{self.transformer_name} transformation applied for SENDING_APP: {sending_app}"

    def _get_sending_app(self, hl7_msg: Any) -> str:
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
