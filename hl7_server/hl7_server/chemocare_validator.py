import logging

from hl7apy.core import Message

from .hl7_constant import Hl7Constants
from .hl7_validator import ValidationException

logger = logging.getLogger(__name__)


class ChemocareValidator:
    """Validates HL7 messages from Chemocare systems based on authority codes and message types."""

    def __init__(self) -> None:
        self.required_hl7_version = Hl7Constants.CHEMOCARE_HL7_VERSION
        self.supported_message_types = Hl7Constants.CHEMOCARE_SUPPORTED_MESSAGE_TYPES
        self.valid_authority_codes = Hl7Constants.CHEMOCARE_AUTHORITY_CODES

    def validate(self, message: Message) -> str:
        """
        Validates a Chemocare HL7 message and returns the authority code.

        Args:
            message: The HL7 message to validate

        Returns:
            str: The authority code (MSH.3 value) for valid messages

        Raises:
            ValidationException: If the message is invalid
        """
        # Validate HL7 version
        message_version = message.msh.msh_12.value
        if message_version != self.required_hl7_version:
            raise ValidationException(
                f"Invalid HL7 version. Expected {self.required_hl7_version}, got {message_version}"
            )

        # Validate authority code (MSH.3)
        authority_code = message.msh.msh_3.value
        if authority_code not in self.valid_authority_codes:
            raise ValidationException(
                f"Invalid authority code. Expected one of {list(self.valid_authority_codes.keys())}, got {authority_code}"
            )

        # Validate message type (MSH.9.2 - trigger event)
        trigger_event = message.msh.msh_9.trigger_event.value
        if trigger_event not in self.supported_message_types:
            raise ValidationException(
                f"Unsupported message type. Expected one of {self.supported_message_types}, got {trigger_event}"
            )

        logger.info(
            f"Valid Chemocare message: Authority Code={authority_code} ({self.valid_authority_codes[authority_code]}), "
            f"Message Type={trigger_event}, Version={message_version}"
        )

        return authority_code

    def get_health_board_name(self, authority_code: str) -> str:
        """Returns the health board name for the given authority code."""
        return self.valid_authority_codes.get(authority_code, "Unknown")
