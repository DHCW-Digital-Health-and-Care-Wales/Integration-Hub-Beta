from field_utils_lib import get_hl7_field_value, set_nested_field
from hl7apy.core import Message

from ..clients.reference_data_client import ReferenceDataLookupClient, ReferenceDataset
from ..utils.remove_timezone_from_datetime import remove_timezone_from_datetime

# ---------------------------------------------------------------------------
# Reference-data enrichment.
#
# The PIMS -> MPI flow must translate the source codes carried by PIMS (HL7 v2.3.1) into the
# codes the eMPI expects for gender, marital status, ethnic group and NHS number status. The
# authoritative mappings live behind the reference-data REST API (see the SBU PIMS ADT Mapping
# Document); each code is resolved at runtime via ``ReferenceDataLookupClient``.
# ---------------------------------------------------------------------------

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


def _apply_reference_lookups(
    original_pid: Message, new_message: Message, lookup_client: ReferenceDataLookupClient
) -> None:
    """Enrich the target PID with eMPI codes for gender, marital status, ethnic group and NHS
    number status, resolved via the reference-data lookup API.

    Each field is enriched only when a source value is present; empty or HL7-null source values are
    left unset. A lookup that fails or returns a malformed code raises
    ``ReferenceDataLookupError`` (a ``ValueError``), which the transformer pipeline logs to the
    monitoring solution and which leaves the message queued. See the SBU PIMS ADT Mapping Document
    for the authoritative rules.
    """
    # PID.8 (Gender): source PID.8 -> target PID.8
    gender_source = get_hl7_field_value(original_pid, "pid_8")
    if not _is_empty_or_hl7_null(gender_source):
        new_message.pid.pid_8 = lookup_client.lookup(ReferenceDataset.GENDER, gender_source)

    # PID.16 (Marital status): source PID.16.CE.1 -> target PID.16.CE.1
    marital_source = get_hl7_field_value(original_pid, "pid_16.ce_1")
    if not _is_empty_or_hl7_null(marital_source):
        new_message.pid.pid_16.ce_1 = lookup_client.lookup(ReferenceDataset.MARITAL_STATUS, marital_source)

    # PID.22 (Ethnic group): source PID.22.CE.1 -> target PID.22.CE.1
    ethnicity_source = get_hl7_field_value(original_pid, "pid_22.ce_1")
    if not _is_empty_or_hl7_null(ethnicity_source):
        new_message.pid.pid_22.ce_1 = lookup_client.lookup(ReferenceDataset.ETHNIC_GROUP, ethnicity_source)

    # PID.32 (NHS number status): source PID.3 (NI) CX.2 -> target PID.32
    nhs_status_source = _get_nhs_number_status_source(original_pid)
    if not _is_empty_or_hl7_null(nhs_status_source):
        new_message.pid.pid_32 = lookup_client.lookup(ReferenceDataset.NHS_STATUS, nhs_status_source)


def map_pid(
    original_hl7_message: Message, new_message: Message, lookup_client: ReferenceDataLookupClient
) -> None:
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

    # Enrich gender / marital status / ethnic group / NHS number status via the reference-data
    # lookup API (replaces the source codes with the codes the eMPI expects).
    _apply_reference_lookups(original_pid, new_message, lookup_client)
