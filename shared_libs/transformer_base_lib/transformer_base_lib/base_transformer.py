from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from hl7apy.core import Message


class BaseTransformer(ABC):
    """Abstract base class for HL7 transformers.
    
    Provides a standardised interface for creating HL7 message transformers.
    """

    def __init__(self, transformer_name: str, config_path: Optional[str] = None):

        self.transformer_name = transformer_name
        self.config_path = config_path or self._get_default_config_path()

    @abstractmethod
    def transform_message(self, hl7_msg: Message) -> Message:
        pass

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
        return os.path.join(os.path.dirname(__file__), "config.ini")

    def run(self) -> None:
        from .run_transformer import run_transformer_app
        run_transformer_app(self)
