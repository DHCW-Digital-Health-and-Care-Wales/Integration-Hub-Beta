"""Builds LIMS HL7v2 XML (shaped like the real LIMS SOAP payload) and converts it with the real xml_to_er7.

The REST server publishes ``xml_to_er7`` output, which drops empty components. Going through the real converter
keeps these fixtures in the same "compacted" layout the transformer actually receives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from hl7_validation.convert import xml_to_er7

NS = "urn:hl7-org:v2xml"

_EMPTY_HD = "<ns0:HD.1/><ns0:HD.2/><ns0:HD.3/>"
_EMPTY_CWE = "".join(f"<ns0:CWE.{i}/>" for i in range(1, 10))


@dataclass(frozen=True)
class Identifier:
    value: str
    authority: str
    id_type: str = "PI"


@dataclass(frozen=True)
class Patient:
    identifiers: list[Identifier]
    merged_id: Identifier | None = None  # emits an MRG when set


@dataclass
class LimsMessage:
    trigger_event: str
    structure: str
    patients: list[Patient] = field(default_factory=list)


def _cx(tag: str, identifier: Identifier) -> str:
    return (
        f"<ns0:{tag}>"
        f"<ns0:CX.1>{escape(identifier.value)}</ns0:CX.1><ns0:CX.2/><ns0:CX.3/>"
        f"<ns0:CX.4><ns0:HD.1>{escape(identifier.authority)}</ns0:HD.1><ns0:HD.2/><ns0:HD.3/></ns0:CX.4>"
        f"<ns0:CX.5>{escape(identifier.id_type)}</ns0:CX.5>"
        f"<ns0:CX.6>{_EMPTY_HD}</ns0:CX.6><ns0:CX.7/><ns0:CX.8/>"
        f"<ns0:CX.9>{_EMPTY_CWE}</ns0:CX.9><ns0:CX.10>{_EMPTY_CWE}</ns0:CX.10>"
        f"</ns0:{tag}>"
    )


def _pid(patient: Patient) -> str:
    identifiers = "".join(_cx("PID.3", i) for i in patient.identifiers)
    return f"<ns0:PID><ns0:PID.1>1</ns0:PID.1>{identifiers}<ns0:PID.8>M</ns0:PID.8></ns0:PID>"


def _mrg(identifier: Identifier) -> str:
    return f"<ns0:MRG>{_cx('MRG.1', identifier)}</ns0:MRG>"


def _msh(message: LimsMessage) -> str:
    return (
        "<ns0:MSH><ns0:MSH.1>|</ns0:MSH.1><ns0:MSH.2>^~\\&amp;</ns0:MSH.2>"
        "<ns0:MSH.3><ns0:HD.1>328</ns0:HD.1><ns0:HD.2/><ns0:HD.3/></ns0:MSH.3>"
        f"<ns0:MSH.9><ns0:MSG.1>ADT</ns0:MSG.1><ns0:MSG.2>{message.trigger_event}</ns0:MSG.2>"
        f"<ns0:MSG.3>{message.structure}</ns0:MSG.3></ns0:MSH.9>"
        "<ns0:MSH.10>LIMS_TEST_MSG</ns0:MSH.10>"
        "<ns0:MSH.11><ns0:PT.1>P</ns0:PT.1><ns0:PT.2/></ns0:MSH.11>"
        "<ns0:MSH.12><ns0:VID.1>2.5</ns0:VID.1></ns0:MSH.12></ns0:MSH>"
    )


def build_lims_xml(message: LimsMessage) -> str:
    body = _msh(message) + f"<ns0:EVN><ns0:EVN.1>{message.trigger_event}</ns0:EVN.1></ns0:EVN>"
    if message.structure == "ADT_A39":
        # A40: each patient (and optional MRG) sits inside its own ADT_A39.PATIENT group.
        for patient in message.patients:
            mrg = _mrg(patient.merged_id) if patient.merged_id else ""
            body += f"<ns0:ADT_A39.PATIENT>{_pid(patient)}{mrg}</ns0:ADT_A39.PATIENT>"
    else:
        body += "".join(_pid(p) for p in message.patients)
        body += "<ns0:PV1><ns0:PV1.1>1</ns0:PV1.1><ns0:PV1.2>N</ns0:PV1.2></ns0:PV1>"
    return f'<ns0:{message.structure} xmlns:ns0="{NS}">{body}</ns0:{message.structure}>'


def lims_er7(message: LimsMessage) -> str:
    """ER7 exactly as the REST server publishes it (via xml_to_er7)."""
    return xml_to_er7(build_lims_xml(message))
