import os

from hl7apy.core import Message
from transformer_base_lib import BaseTransformer

from .mappers.additional_segment_mapper import map_non_specific_segments
from .mappers.evn_mapper import map_evn
from .mappers.mrg_mapper import map_mrg
from .mappers.msh_mapper import map_msh
from .mappers.pd1_mapper import map_pd1
from .mappers.pid_mapper import map_pid
from .mappers.pv1_mapper import map_pv1


def transform_pims_message(original_hl7_msg: Message) -> Message:
    new_message = Message(version="2.5")

    map_msh(original_hl7_msg, new_message)
    map_evn(original_hl7_msg, new_message)
    map_pid(original_hl7_msg, new_message)
    map_pd1(original_hl7_msg, new_message)
    map_pv1(original_hl7_msg, new_message)
    map_mrg(original_hl7_msg, new_message)

    map_non_specific_segments(original_hl7_msg, new_message)

    return new_message


class PimsTransformer(BaseTransformer):

    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("PIMS", config_path)

    def transform_message(self, hl7_msg: Message) -> Message:
        return transform_pims_message(hl7_msg)
