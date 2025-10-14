import os

from hl7apy.core import Field, Message
from transformer_base_lib import BaseTransformer

from .date_of_death_transformer import transform_date_of_death
from .datetime_transformer import transform_datetime


class PhwTransformer(BaseTransformer):

    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("PHW", config_path)

    def transform_message(self, hl7_msg: Message) -> Message:
        msh_segment = hl7_msg.msh

        # Transform datetime
        created_datetime = msh_segment.msh_7.value
        transformed_datetime = transform_datetime(created_datetime)
        msh_segment.msh_7.value = transformed_datetime

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

        return hl7_msg

