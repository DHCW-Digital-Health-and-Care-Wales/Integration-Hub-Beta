"""Mappers Package for Training HL7 Transformer.

This package contains mappers for transforming individual HL7 segments.
Each mapper follows a similar pattern:
1. Takes the original message and new message as input
2. Copies fields from original to new, applying transformations
3. Returns any transformation details for logging/auditing

AVAILABLE MAPPERS:
-----------------
- map_msh: MSH (Message Header) segment mapper
           Includes WEEK 2 EXERCISE 1 SOLUTION: DateTime transformation

- map_evn: EVN (Event Type) segment mapper
           WEEK 2 EXERCISE 2 SOLUTION: Bulk copy of EVN fields

- map_pid: PID (Patient Identification) segment mapper
           WEEK 2 EXERCISE 3 SOLUTION: Bulk copy + name uppercasing
"""

from training_hl7_transformer.mappers.evn_mapper import map_evn
from training_hl7_transformer.mappers.msh_mapper import map_msh
from training_hl7_transformer.mappers.pid_mapper import map_pid

__all__ = ["map_msh", "map_evn", "map_pid"]