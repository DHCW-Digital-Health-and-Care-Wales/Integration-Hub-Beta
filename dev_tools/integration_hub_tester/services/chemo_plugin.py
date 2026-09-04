"""Chemocare Transformer plugin.

transform_chemocare_message() is a standalone function — no class init needed.
"""
from __future__ import annotations

from .base import ServicePlugin

_CHEMO_A31_SW = """\
MSH|^~\\&|192|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.4|||NE|NE
EVN|Sub|20250624161510
PID|1|1000000001^^^^NH|1000000001^^^^NH~B1000001^^^^PAS||TEST^TEST^^^Mrs.||20000101000000|F|||1 TEST TEST TEST TEST^TEST^TEST^TEST^CF11 9AD||01000 000001^PRN|01000 000001^WPN||||||||||||||||||1
PD1||||G7000001
PV1||U"""

_CHEMO_A28_SW = """\
MSH|^~\\&|192|192|200|200|20250701154910||ADT^A28|474997159036153|P|2.4|||NE|NE
EVN|Sub|20250701154910
PID|1|1000000001^^^^NH|1000001^^^^PAS~1000000001^^^^NH||TEST^TEST^TEST^^Mr.||20000101000000|M|||^^^^CF11 9AD||01000 000001^PRN^^test@test.com~07000000001^PRS|07000000001^WPN||||||||||||||||||1
PD1||||G7000001
PV1||U"""

_CHEMO_A28_VEL = """\
MSH|^~\\&|224|224|100|100|20250624165855||ADT^A28|951317629075403|P|2.4|||NE|NE
EVN|Sub|20250624165855
PID|1|1000000001^^^^NH|1000000001^^^^NH~V1000001^^^^PAS||TEST^TEST^^^Mrs.||20000101000000|F|||^^^^CF11 9AD||07000000001^PRN^^test@test.co.uk~07000000001^PRS~07000000001^PRN^^test@test.co.uk~|07000000001^WPN||||||||||||||||||1
PD1||||G7000001
PV1||U"""


class ChemoPlugin(ServicePlugin):
    tab_label = "Chemo Transformer"
    description = "ChemoCare HL7v2 → normalised HL7v2 v2.5"
    input_label = "HL7v2 ER7 Input  (ADT A28 / A31 from ChemoCare)"
    output_label = "Transformed HL7v2 ER7 Output"
    button_label = "▶  Transform"
    samples = {
        "A31 Southwest": _CHEMO_A31_SW,
        "A28 Southwest": _CHEMO_A28_SW,
        "A28 Velindre": _CHEMO_A28_VEL,
    }

    def __init__(self) -> None:
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from hl7apy.parser import parse_message

        from hl7_chemo_transformer.chemocare_transformer import transform_chemocare_message

        er7 = input_text.strip().replace("\n", "\r")
        msg = parse_message(er7, find_groups=False)
        result = transform_chemocare_message(msg)
        output = result.to_er7().replace("\r", "\n")
        return output, "✓  Chemocare transformation applied"
