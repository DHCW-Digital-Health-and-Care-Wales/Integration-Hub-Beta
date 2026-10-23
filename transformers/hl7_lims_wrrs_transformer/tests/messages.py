"""HL7 ER7 fixtures for the LIMS WRRS transformer tests."""
from __future__ import annotations

NHS_AND_LIMS_IDS = "1234567^^^NHS^NH~L123^^^328^PI"
LIMS_ONLY_IDS = "L123^^^328^PI"
NHS_ONLY_IDS = "1234567^^^NHS^NH"


def build_adt(trigger_event: str, pid_3: str, structure: str = "ADT_A05", with_mrg: bool = False) -> str:
    segments = [
        f"MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^{trigger_event}^{structure}|MSG0001|P|2.5",
        "EVN||20260101120000",
        f"PID|1||{pid_3}||SMITH^JOHN||19800101|M",
        "PV1|1|N",
    ]
    if with_mrg:
        segments.append("MRG|OLD123^^^328^PI")
    return "\r".join(segments)


A31_NHS_AND_LIMS = build_adt("A31", NHS_AND_LIMS_IDS)
A31_LIMS_ONLY = build_adt("A31", LIMS_ONLY_IDS)
A40_NHS_AND_LIMS = build_adt("A40", NHS_AND_LIMS_IDS, structure="ADT_A39", with_mrg=True)
A40_LIMS_ONLY = build_adt("A40", LIMS_ONLY_IDS, structure="ADT_A39", with_mrg=True)
A40_NHS_ONLY_NO_MRG = build_adt("A40", NHS_ONLY_IDS, structure="ADT_A39")
A04_NHS_AND_LIMS = build_adt("A04", NHS_AND_LIMS_IDS)
