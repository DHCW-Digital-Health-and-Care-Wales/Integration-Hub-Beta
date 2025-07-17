# import logging

from hl7apy.core import Message

# logger = logging.getLogger(__name__)


def transform_chemocare(hl7_msg: Message) -> Message:
    # logger.debug("Applying Chemocare transformation")
    _transform_msh_segment(hl7_msg)
    # logger.debug("Chemocare transformation completed")
    return hl7_msg


def _transform_msh_segment(hl7_msg: Message) -> None:
    msh = hl7_msg.msh

    # MSH.9/MSG.3 = "ADT_A05"
    if hasattr(msh, "msh_9") and msh.msh_9:
        msh.msh_9.msh_9_3 = "ADT_A05"

    # MSH.12/VID.1 = "2.5"
    if hasattr(msh, "msh_12") and msh.msh_12:
        msh.msh_12.msh_12_1 = "2.5"

# Used to access HL7 nested fields directly (without crashing)
def _safe_get_value(segment, field_path: str) -> str:
    try:
        current = segment
        for part in field_path.split("."):
            current = getattr(current, part)
        return current.value if hasattr(current, "value") else str(current)
    except (AttributeError, IndexError):
        return ""
