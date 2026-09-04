"""PHW Transformer plugin.

Wraps PhwTransformer.transform_message() without triggering
BaseTransformer.__init__ (which would try to connect to Service Bus).
"""
from __future__ import annotations

from .base import ServicePlugin

_PHW_SAMPLE = """\
MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|202505052323326666666666|P|2.5|||||GBR||EN
EVN||20250502102000|20250505232328|||20250505232328
PID|||8888888^^^252^PI~6666666666^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19870101|M|^^||ADDRESS1^ADDRESS2^ADDRESS3^ADDRESS4^XX99 9XX^^H~^^^^^^||^^^~|||||||||||||||||||01
PD1|||^^W99999^|G7777777
PV1||U"""

_PHW_SAMPLE_A31 = """\
MSH|^~\\&|192|192|200|200|20250624161510||ADT^A31|369913945290925|P|2.4|||NE|NE
EVN|Sub|20250624161510
PID|1|1000000001^^^^NH|1000000001^^^^NH~B1000001^^^^PAS||TEST^TEST^^^Mrs.||20000101000000|F|||1 TEST TEST TEST TEST^TEST^TEST^TEST^CF11 9AD||01000 000001^PRN|01000 000001^WPN||||||||||||||||||1
PD1||||G7000001
PV1||U"""


class PhwPlugin(ServicePlugin):
    tab_label = "PHW Transformer"
    description = "Public Health Wales HL7v2 → normalised HL7v2 v2.5"
    input_label = "HL7v2 ER7 Input  (ADT A28 / A31 from PHW)"
    output_label = "Transformed HL7v2 ER7 Output"
    button_label = "▶  Transform"
    samples = {
        "A28 (PHW fixture)": _PHW_SAMPLE,
        "A31 (Southwest)": _PHW_SAMPLE_A31,
    }

    def __init__(self) -> None:
        # dataclass __init__ is not used — attributes are class-level defaults.
        pass

    def run(self, input_text: str) -> tuple[str, str]:
        from hl7apy.parser import parse_message

        from hl7_phw_transformer.phw_transformer import PhwTransformer

        er7 = input_text.strip().replace("\n", "\r")
        msg = parse_message(er7, find_groups=False)

        # Bypass BaseTransformer.__init__ (Service Bus setup) — only the two
        # instance attributes set in PhwTransformer.__init__ are needed here.
        transformer: PhwTransformer = object.__new__(PhwTransformer)
        transformer._current_datetime_transformation = None
        transformer._current_dod_transformation = None

        result = transformer.transform_message(msg)
        output = result.to_er7().replace("\r", "\n")

        audit = transformer.get_processed_audit_text(msg)
        return output, f"✓  {audit}"
