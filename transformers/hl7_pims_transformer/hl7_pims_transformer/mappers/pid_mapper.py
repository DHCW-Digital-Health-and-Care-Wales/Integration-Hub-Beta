from field_utils_lib import get_hl7_field_value, set_nested_field
from hl7apy.core import Message

from ..utils.remove_timezone_from_datetime import remove_timezone_from_datetime

# ---------------------------------------------------------------------------
# Placeholder enrichment values.
#
# These fixed placeholder strings are a temporary stand-in for a future shared
# lookup mechanism (see the "Value Lookup Tables for Transformers" spike). Each PID
# field that the PIMS -> MPI flow must translate is set to its placeholder whenever a
# source value is present. The authoritative mappings live in the SBU PIMS ADT
# Mapping Document; replace these placeholders once the real reference-data source is
# available.
# ---------------------------------------------------------------------------

# PID.8 (Administrative sex).
_GENDER_PLACEHOLDER = "GenderPlaceholder"
# PID.16 (Marital status), CE.1.
_MARITAL_STATUS_PLACEHOLDER = "MaritalStatusPlaceholder"
# PID.22 (Ethnic group), CE.1.
_ETHNICITY_PLACEHOLDER = "EthnicityPlaceholder"
# PID.32 (NHS number status).
_NHS_NUMBER_STATUS_PLACEHOLDER = "NHSNumberStatusPlaceholder"

# HL7 NULL is represented as a pair of double quotes.
_HL7_NULL = '""'


def _is_empty_or_hl7_null(value: str) -> bool:
    """Return True for an absent, blank or explicit HL7-null ("") source value."""
    stripped = value.strip()
    return stripped == "" or stripped == _HL7_NULL


def _get_nhs_number_status_source(original_pid: Message) -> str:
    """Return the NHS number status code (CX.2) from the PID.3 'NI' repetition.

    PID.32 (NHS number status) does not exist in HL7 v2.3.1, so the source value is
    taken from the check-code component of the NHS-number (NI) identifier repetition.
    Returns an empty string when no NI repetition is present.
    """
    for pid_3_repetition in getattr(original_pid, "pid_3", []):
        cx_5 = (get_hl7_field_value(pid_3_repetition, "cx_5") or "").strip().upper()
        if cx_5 == "NI":
            return (get_hl7_field_value(pid_3_repetition, "cx_2") or "").strip()
    return ""


def _apply_reference_lookups(original_pid: Message, new_message: Message) -> None:
    """Enrich the target PID with placeholder values for gender, marital status,
    ethnic group and NHS number status.

    Each field is set to its fixed placeholder only when a source value is present;
    empty or HL7-null source values are left unset. See the SBU PIMS ADT Mapping
    Document for the authoritative rules.
    """
    # PID.8 (Gender): source PID.8 -> target PID.8
    if not _is_empty_or_hl7_null(get_hl7_field_value(original_pid, "pid_8")):
        new_message.pid.pid_8 = _GENDER_PLACEHOLDER

    # PID.16 (Marital status): source PID.16.CE.1 -> target PID.16.CE.1
    if not _is_empty_or_hl7_null(get_hl7_field_value(original_pid, "pid_16.ce_1")):
        new_message.pid.pid_16.ce_1 = _MARITAL_STATUS_PLACEHOLDER

    # PID.22 (Ethnic group): source PID.22.CE.1 -> target PID.22.CE.1
    if not _is_empty_or_hl7_null(get_hl7_field_value(original_pid, "pid_22.ce_1")):
        new_message.pid.pid_22.ce_1 = _ETHNICITY_PLACEHOLDER

    # PID.32 (NHS number status): source PID.3 (NI) CX.2 -> target PID.32
    if not _is_empty_or_hl7_null(_get_nhs_number_status_source(original_pid)):
        new_message.pid.pid_32 = _NHS_NUMBER_STATUS_PLACEHOLDER


def map_pid(original_hl7_message: Message, new_message: Message) -> None:
    original_pid = getattr(original_hl7_message, "pid", None)
    if not original_pid:
        return  # No PID segment

    original_pid3_repetitions = getattr(original_pid, "pid_3", [])

    # PID.3[1] (index 0): map if CX.1 is present and CX.5 == 'NI'
    if len(original_pid3_repetitions) >= 1:
        cx1_rep1 = (get_hl7_field_value(original_pid, "pid_3[0].cx_1") or "").strip()
        cx5_rep1 = (get_hl7_field_value(original_pid, "pid_3[0].cx_5") or "").strip().upper()
        if cx1_rep1 and cx5_rep1 == "NI":
            pid3_rep1 = new_message.pid.add_field("pid_3")
            pid3_rep1.cx_1 = cx1_rep1
            pid3_rep1.cx_4.hd_1 = "NHS"
            pid3_rep1.cx_5 = "NH"

    # PID.3[2] (index 1): map if CX.1 is present and CX.5 == 'PI'
    if len(original_pid3_repetitions) >= 2:
        cx1_rep2 = (get_hl7_field_value(original_pid, "pid_3[1].cx_1") or "").strip()
        cx5_rep2 = (get_hl7_field_value(original_pid, "pid_3[1].cx_5") or "").strip().upper()
        if cx1_rep2 and cx5_rep2 == "PI":
            pid3_rep2 = new_message.pid.add_field("pid_3")
            pid3_rep2.cx_1 = cx1_rep2
            pid3_rep2.cx_4.hd_1 = "103"
            pid3_rep2.cx_5 = "PI"

    set_nested_field(original_pid, new_message.pid, "pid_5.xpn_1.fn_1")

    pid_5_fields = ["xpn_2", "xpn_3", "xpn_4", "xpn_5"]
    for field in pid_5_fields:
        set_nested_field(original_pid, new_message.pid, f"pid_5.{field}")

    # PID.7 - remove timezone from timestamp for MPI compatibility
    original_pid7_ts1 = get_hl7_field_value(original_pid, "pid_7.ts_1")
    if original_pid7_ts1:
        new_message.pid.pid_7.ts_1 = remove_timezone_from_datetime(original_pid7_ts1)

    set_nested_field(original_pid, new_message.pid, "pid_8")

    # SAD does not exist in HL7 v2.3.1 so it's mapped manually
    new_message.pid.pid_11.xad_1.sad_1 = original_pid.pid_11.xad_1

    pid_11_fields = ["xad_2", "xad_3", "xad_4", "xad_5"]
    for field in pid_11_fields:
        set_nested_field(original_pid, new_message.pid, f"pid_11.{field}")

    # Map all repetitions of pid_13
    if hasattr(original_pid, "pid_13"):
        for rep_count, original_pid_13 in enumerate(original_pid.pid_13):
            new_pid_13_repetition = new_message.pid.add_field("pid_13")
            set_nested_field(original_pid_13, new_pid_13_repetition, "xtn_1")

    set_nested_field(original_pid, new_message.pid, "pid_14.xtn_1")

    # Death date and time: trim at first "+" if length > 6, otherwise set to '""'
    original_pid29_ts1 = get_hl7_field_value(original_pid, "pid_29.ts_1")
    new_message.pid.pid_29.ts_1 = (
        remove_timezone_from_datetime(original_pid29_ts1) if len(original_pid29_ts1) > 6 else '""'
    )

    # Enrich gender / marital status / ethnic group / NHS number status using the
    # hardcoded placeholder tables above (to be replaced by a real lookup source).
    _apply_reference_lookups(original_pid, new_message)
