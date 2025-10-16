import os
from typing import Optional

from hl7apy.core import Field, Message
from transformer_base_lib import BaseTransformer

from .date_of_death_transformer import transform_date_of_death
from .datetime_transformer import transform_datetime


class PhwTransformer(BaseTransformer):

    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("PHW", config_path)
        self._transformation_details: list[str] = []
        self._original_datetime: Optional[str] = None
        self._transformed_datetime: Optional[str] = None
        self._original_dod: Optional[str] = None
        self._transformed_dod: Optional[str] = None

    def transform_message(self, hl7_msg: Message) -> Message:
        # Reset transformation details for this message
        self._transformation_details = []
        self._original_datetime = None
        self._transformed_datetime = None
        self._original_dod = None
        self._transformed_dod = None

        msh_segment = hl7_msg.msh

        # Transform datetime
        created_datetime = msh_segment.msh_7.value
        transformed_datetime = transform_datetime(created_datetime)
        msh_segment.msh_7.value = transformed_datetime

        # Track datetime transformation
        self._original_datetime = created_datetime
        self._transformed_datetime = transformed_datetime
        self._transformation_details.append(
            f"DateTime transformed from {created_datetime} to {transformed_datetime}"
        )

        # Transform date of death
        pid_segment = getattr(hl7_msg, "pid", None)
        if pid_segment:
            dod_field = getattr(pid_segment, "pid_29", None)
            original_dod = getattr(dod_field, "value", dod_field)

            if original_dod is not None:
                transformed_dod = transform_date_of_death(original_dod)

                if isinstance(dod_field, Field) and hasattr(dod_field, "value"):
                    dod_field.value = transformed_dod
                else:
                    pid_segment.pid_29 = transformed_dod

                # Track date of death transformation
                self._original_dod = original_dod
                self._transformed_dod = transformed_dod
                self._transformation_details.append(
                    f'Date of death transformed from {original_dod} to {transformed_dod}'
                )

        return hl7_msg

    def get_processed_audit_text(self, hl7_msg: Message) -> str:
        if self._transformation_details:
            transformations = "; ".join(self._transformation_details)
            return f"HL7 transformations applied: {transformations}"
        return super().get_processed_audit_text(hl7_msg)

