"""Shared constants for hl7_message_processor."""

from typing import Dict, Tuple

HL7_XML_NAMESPACE = "urn:hl7-org:v2xml"

# HL7 segment name constants used in a few places across the package.
MSH_SEGMENT = "MSH"
MSH_FIELD_SEPARATOR_INDEX = 2
OBX_SEGMENT = "OBX"
OBX_VALUE_TYPE_FIELD = 2

# Upper bounds on the numbers accepted from XML tag suffixes (``PID.3``, ``CX.4``) in ``xml_to_er7``. The
# suffix is attacker-controlled and sizes the padding list built for it, so an unbounded value (e.g.
# ``<PID.999999999/>``) could exhaust the worker's memory. The values are the largest numbers that occur in
# the bundled schemas (2.4, 2.5, 2.5.1 and 2.6): ``IN2.72`` for a segment field and ``PPN.24`` for a datatype
# component. ``tests/test_converter.py`` fails if a bundled schema ever exceeds them.
MAX_XML_FIELD_NUMBER = 72
MAX_XML_COMPONENT_NUMBER = 24

# Segment fields whose actual HL7 data type is only known at runtime, from the value of another
# field in the same segment, rather than being fixed by the schema. Maps (segment, field_number)
# -> the field_number holding the HL7 datatype code to use when rendering the variable field's
# XML structure. OBX-5 (Observation Value) is HL7's canonical example: its schema type is
# declared as "varies"/"xsd:anyType" (see custom_schemas/2_5_1/ORU_R01_2_5_1.xsd) and is only
# resolvable from OBX-2 (Value Type) at runtime.
VARIABLE_DATATYPE_FIELDS: Dict[Tuple[str, int], int] = {
    (OBX_SEGMENT, 5): OBX_VALUE_TYPE_FIELD,
}
