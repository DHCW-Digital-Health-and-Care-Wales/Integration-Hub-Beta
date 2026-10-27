"""Safe extraction of the HL7 fields used to resolve version + message structure.

Reuses ``field_utils_lib.get_hl7_field_value`` (a genuine shared, general-purpose utility, not part of
``hl7_validation``) for the actual field traversal - see
notes/hl7-message-processor-design-report.md section 5.5.
"""

from typing import Any

from field_utils_lib.field_utils import get_hl7_field_value
from hl7apy.parser import parse_message


def parse_er7_message(er7_message: str) -> Any:
    """Parse an ER7 string into an hl7apy Message, without hl7apy's own group detection.

    ``find_groups=False`` matches hl7_validation's convention: this package does its own group
    detection (see matcher.py) driven by the resolved XSD, rather than hl7apy's built-in grouping.
    """
    return parse_message(er7_message, find_groups=False)


def get_version(msg: Any) -> str:
    """MSH-12.1 - the HL7 version, e.g. "2.5.1"."""
    return get_hl7_field_value(msg.msh, "msh_12.msh_12_1")

def get_sendingapp(msg: Any) -> str:
    """MSH-3-1 - the sending application."""
    return get_hl7_field_value(msg.msh, "msh_3.msh_3_1")

def get_receivingapp(msg: Any) -> str:
    """MSH-5-1 - the receiving application."""
    return get_hl7_field_value(msg.msh, "msh_5.msh_5_1")

def get_controll_id(msg: Any) -> str:
    """MSH-10 - the message control ID."""
    return get_hl7_field_value(msg.msh, "msh_10")

def get_message_code(msg: Any) -> str:
    """MSH-9.1 - the message code, e.g. "ADT"."""
    return get_hl7_field_value(msg.msh, "msh_9.msh_9_1")


def get_trigger_event(msg: Any) -> str:
    """MSH-9.2 - the trigger event, e.g. "A28"."""
    return get_hl7_field_value(msg.msh, "msh_9.msh_9_2")


def get_structure_id(msg: Any) -> str:
    """MSH-9.3 - the message structure, e.g. "ADT_A05", when explicitly present on the wire."""
    return get_hl7_field_value(msg.msh, "msh_9.msh_9_3")


def normalise_version(raw_version: str) -> str:
    """Normalise a raw MSH-12.1 value (e.g. "2.5.1") to a schema folder key (e.g. "2_5_1")."""
    return raw_version.strip().replace(".", "_")
