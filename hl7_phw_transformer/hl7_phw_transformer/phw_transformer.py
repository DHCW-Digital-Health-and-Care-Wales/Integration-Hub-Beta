import os
from typing import Optional

from hl7apy.core import Message
from transformer_base_lib import BaseTransformer

from .mappers.additional_segment_mapper import map_non_specific_segments
from .mappers.msh_mapper import map_msh
from .mappers.pid_mapper import map_pid


def transform_phw_message(
    original_hl7_msg: Message,
) -> tuple[Message, Optional[tuple[str, str]], Optional[tuple[str, str]]]:

    new_message = Message(version="2.5")

    datetime_transformation = map_msh(original_hl7_msg, new_message)
    dod_transformation = map_pid(original_hl7_msg, new_message)
    map_non_specific_segments(original_hl7_msg, new_message)

    return new_message, datetime_transformation, dod_transformation


class PhwTransformer(BaseTransformer):

    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("PHW", config_path)
        self._current_datetime_transformation: Optional[tuple[str, str]] = None
        self._current_dod_transformation: Optional[tuple[str, str]] = None

    def transform_message(self, hl7_msg: Message) -> Message:
        new_message, datetime_transformation, dod_transformation = transform_phw_message(
            hl7_msg
        )

        self._current_datetime_transformation = datetime_transformation
        self._current_dod_transformation = dod_transformation

        return new_message

    def get_processed_audit_text(self, hl7_msg: Message) -> str:
        transformation_details = []

        if self._current_datetime_transformation:
            original_dt, transformed_dt = self._current_datetime_transformation
            transformation_details.append(
                f"DateTime transformed from {original_dt} to {transformed_dt}"
            )

        if self._current_dod_transformation:
            original_dod, transformed_dod = self._current_dod_transformation
            transformation_details.append(
                f"Date of death transformed from {original_dod} to {transformed_dod}"
            )

        if transformation_details:
            transformations = "; ".join(transformation_details)
            return f"HL7 transformations applied: {transformations}"

        return super().get_processed_audit_text(hl7_msg)

