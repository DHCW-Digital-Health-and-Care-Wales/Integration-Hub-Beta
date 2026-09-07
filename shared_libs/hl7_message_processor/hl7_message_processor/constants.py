"""Shared constants for hl7_message_processor."""

from typing import Dict, Tuple

HL7_XML_NAMESPACE = "urn:hl7-org:v2xml"

# HL7 segment name constants used in a few places across the package.
MSH_SEGMENT = "MSH"
MSH_FIELD_SEPARATOR_INDEX = 2
OBX_SEGMENT = "OBX"
OBX_VALUE_TYPE_FIELD = 2

# Segment fields whose actual HL7 data type is only known at runtime, from the value of another
# field in the same segment, rather than being fixed by the schema. Maps (segment, field_number)
# -> the field_number holding the HL7 datatype code to use when rendering the variable field's
# XML structure. OBX-5 (Observation Value) is HL7's canonical example: its schema type is
# declared as "varies"/"xsd:anyType" (see custom_schemas/2_5_1/ORU_R01_2_5_1.xsd) and is only
# resolvable from OBX-2 (Value Type) at runtime.
VARIABLE_DATATYPE_FIELDS: Dict[Tuple[str, int], int] = {
    (OBX_SEGMENT, 5): OBX_VALUE_TYPE_FIELD,
}
