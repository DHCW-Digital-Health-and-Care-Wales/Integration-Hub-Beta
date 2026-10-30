import os
from typing import Dict, Optional

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message
from transformer_base_lib import BaseTransformer

from .clients.reference_data_client import ReferenceDataLookup, ReferenceDataLookupClient
from .mappers.additional_segment_mapper import map_non_specific_segments
from .mappers.evn_mapper import map_evn
from .mappers.mrg_mapper import map_mrg
from .mappers.msh_mapper import map_msh
from .mappers.pd1_mapper import map_pd1
from .mappers.pid_mapper import map_pid
from .mappers.pv1_mapper import map_pv1


def transform_pims_message(original_hl7_msg: Message, lookup_client: ReferenceDataLookup) -> Message:
    new_message = Message(version="2.5")

    # Some PIMS message structures (e.g. ADT_A39 used for the A40/merge trigger event) nest
    # PID/PD1/MRG/PV1 inside a repeating "PATIENT" group when parsed with hl7apy's default
    # find_groups=True. Reparse as a flat structure so every mapper can access segments
    # directly (e.g. original_hl7_msg.pid) regardless of the incoming message structure.
    flat_hl7_msg = parse_message(original_hl7_msg.to_er7(), find_groups=False)

    map_msh(flat_hl7_msg, new_message)
    map_evn(flat_hl7_msg, new_message)
    map_pid(flat_hl7_msg, new_message, lookup_client)
    map_pd1(flat_hl7_msg, new_message)
    map_pv1(flat_hl7_msg, new_message)
    map_mrg(flat_hl7_msg, new_message)

    map_non_specific_segments(flat_hl7_msg, new_message)

    return new_message


class PimsTransformer(BaseTransformer):

    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("PIMS", config_path)
        # Single, thread-safe client reused for every message (built from environment config).
        self._lookup_client = ReferenceDataLookupClient.from_env()

    def transform_message(self, hl7_msg: Message) -> Message:
        return transform_pims_message(hl7_msg, self._lookup_client)

    def get_egress_properties(
        self, incoming_props: Optional[Dict[str, str]], transformed_msg: Message
    ) -> Optional[Dict[str, str]]:
        # MessageType was set from the incoming A04/A08; the transformed topic subscription filters on A28/A31/A40.
        return {**(incoming_props or {}), "MessageType": get_hl7_field_value(transformed_msg, "msh.msh_9.msg_2")}
