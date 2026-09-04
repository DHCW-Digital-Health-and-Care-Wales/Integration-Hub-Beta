"""PIMS Transformer plugin.

transform_pims_message() is a standalone function — no class init needed.
"""
from __future__ import annotations

from .base import ServicePlugin

_PIMS_A04 = """\
MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20250702085450+0000||ADT^A04^ADT_A01|73726643|P|2.3.1
EVN||20250702085440+0000||||20250702085450+0000
PID|||N4000000001^03^^^NI~N1000001^^^^PI||TEST^TEST-TEST^""^^MISS||20000101+^D|F|||1 TEST^TEST^TEST^""^CF11 9AD||07000000001^PRN^PH~07000000001^ORN^CP|07000000001^WPN^PH||S|||||||||||||^D||||20250702085440+0000
PD1||||G7000001~W90001
PV1||NA"""

_PIMS_A08 = """\
MSH|^~\\&|PIMS|BroMor HL7Sender|EMPI|EMPI|20241231101053+0000||ADT^A08^ADT_A01|48209024|P|2.3.1
EVN||20241231101035+0000||||20241231101035+0000
PID|||^03^^^NI~N5022039^^^^PI||TESTER^TEST^""^^MRS.||20000101+^D|F|||MORRISTON HOSPITAL^HEOL MAES EGLWYS^CWMRHYDYCEIRW^SWANSEASWANSEA^SA6 6NL||01234567892^PRN^PH~01234567896^ORN^CP|^WPN^PH||M||||||1|||||||^D||||20241231101035+0000
PD1||||G9310201~W98006
PV1||NA"""

_PIMS_A40 = """\
MSH|^~\\&|PIMS|BroMor HL7Sender|CPI|BroMor|20250630155035+0000||ADT^A40^ADT_A40|73711860|P|2.3.1
EVN||20250630155034+0000||||20250630155034+0000
PID|||1000000001^01^^^NI~T100001^^^^PI||TEST^TEST^TEST^^MS.||20000101+^D|F|||1, TEST^TEST TEST^TEST^TEST^CF11 9AD||07000000001 TEST PTNR^PRN^PH~07000000001 PT^ORN^CP|50500 02920^WPN^PH||S^NONE||||||0|||||||^D||||20250630155034+0000
PD1||||G1000001~W10001
MRG|00100001"""


class PimsPlugin(ServicePlugin):
    tab_label = "PIMS Transformer"
    description = "PIMS HL7v2 → normalised HL7v2 v2.5  (A04 / A08 / A40)"
    input_label = "HL7v2 ER7 Input  (ADT A04 / A08 / A40 from PIMS)"
    output_label = "Transformed HL7v2 ER7 Output"
    button_label = "▶  Transform"
    samples = {
        "A04 (New patient)": _PIMS_A04,
        "A08 (Patient update)": _PIMS_A08,
        "A40 (Merge)": _PIMS_A40,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from hl7apy.parser import parse_message

        from hl7_pims_transformer.pims_transformer import transform_pims_message

        er7 = input_text.strip().replace("\n", "\r")
        msg = parse_message(er7, find_groups=False)
        result = transform_pims_message(msg)
        output = result.to_er7().replace("\r", "\n")
        return output, "✓  PIMS transformation applied"
