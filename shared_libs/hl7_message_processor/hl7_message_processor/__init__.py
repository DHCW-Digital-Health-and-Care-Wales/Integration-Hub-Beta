"""HL7 v2 ER7 <-> XML conversion and validation, selected by (version, message structure).

Public API is re-exported here; see README.md for usage and design_report reference in
notes/hl7-message-processor-design-report.md for the rationale behind the design decisions
in this package.
"""

from .converter import er7_to_xml, xml_to_er7
from .exceptions import MessageNotProcessableError, SchemaNotFoundError, XmlValidationError
from .processor import ProcessedMessage, process_er7
from .schema_resolver import SchemaResolver, resolve_schema_path
from .validator import validate_xml

__all__ = [
    "MessageNotProcessableError",
    "ProcessedMessage",
    "SchemaNotFoundError",
    "SchemaResolver",
    "XmlValidationError",
    "er7_to_xml",
    "process_er7",
    "resolve_schema_path",
    "validate_xml",
    "xml_to_er7",
]
