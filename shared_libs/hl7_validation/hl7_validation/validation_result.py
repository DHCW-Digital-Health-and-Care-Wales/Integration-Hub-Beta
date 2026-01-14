from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    """
    Result of HL7 message validation that includes the generated XML.

    This class encapsulates the validation outcome along with the XML representation
    of the message, allowing downstream processes to store the XML in a database
    without re-converting the message.

    Attributes:
        xml_string: The HL7v2 XML representation of the message
        structure_id: The message structure identifier (e.g., "ADT_A01", "ADT_A05")
        message_type: The message type from MSH-9.1 (e.g., "ADT", "ORM")
        trigger_event: The trigger event from MSH-9.2 (e.g., "A01", "A31")
        message_control_id: The unique message control ID from MSH-10
        is_valid: Whether the message passed validation
        error_message: Error details if validation failed, None otherwise
    """

    xml_string: str
    structure_id: str
    message_type: Optional[str] = None
    trigger_event: Optional[str] = None
    message_control_id: Optional[str] = None
    is_valid: bool = True
    error_message: Optional[str] = None

    def __bool__(self) -> bool:
        return self.is_valid
