from hl7apy import consts
from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException, ValidationError
from hl7apy.parser import parse_message

from .constants import PARSE_ERROR_MSG
from .convert import xml_to_er7
from .validate import XmlValidationError

SUPPORTED_VERSIONS = frozenset({"2.4", "2.5", "2.5.1", "2.6"})
_VERSIONS_STR = ", ".join(sorted(SUPPORTED_VERSIONS))


def _check_version_supported(version: str) -> None:
    """
    Validate that the HL7 version is supported.

    Args:
        version: HL7 version string to check

    Raises:
        XmlValidationError: If version is not in SUPPORTED_VERSIONS
    """
    if version not in SUPPORTED_VERSIONS:
        raise XmlValidationError(f"Unsupported HL7 version '{version}'. Supported versions: {_VERSIONS_STR}")

def validate_er7_with_standard(er7_string: str, version: str) -> None:
    """
    Validate HL7 ER7 message against standard HL7 specification using hl7apy.

    Args:
        er7_string: The HL7 message in ER7 format
        version: HL7 version string (must be in SUPPORTED_VERSIONS)

    Raises:
        XmlValidationError: If validation fails or version is unsupported
    """
    _check_version_supported(version)

    try:
        msg = parse_message(er7_string, validation_level=consts.VALIDATION_LEVEL.STRICT, find_groups=False)
    except (HL7apyException, ValueError) as e:
        raise XmlValidationError(f"{PARSE_ERROR_MSG}: {e}") from e

    try:
        msg.validate()
    except (ValidationError, HL7apyException) as e:
        raise XmlValidationError(f"Standard HL7 v{version} validation failed: {e}") from e


def validate_parsed_message_with_standard(msg: Message, version: str) -> None:
    """
    Validate already-parsed HL7 message against standard HL7 specification.

    Optimized version that accepts pre-parsed message to avoid redundant parsing.

    Args:
        msg: Already parsed HL7 message object
        version: HL7 version string (must be in SUPPORTED_VERSIONS)

    Raises:
        XmlValidationError: If validation fails, version is unsupported, or version mismatch
    """
    _check_version_supported(version)

    msg_version = getattr(msg, 'version', None)
    if msg_version and msg_version != version:
        raise XmlValidationError(
            f"Message version {msg_version} does not match requested version {version}"
        )

    try:
        msg.validate()
    except (ValidationError, HL7apyException) as e:
        raise XmlValidationError(f"Standard HL7 v{version} validation failed: {e}") from e


def validate_xml_with_hl7apy(xml_string: str, version: str) -> None:
    """
    Validate HL7v2 XML message using hl7apy standard validation.

    This function converts the XML to ER7 format and then validates it
    using hl7apy's standard HL7 validation rules.

    Args:
        xml_string: The HL7 message in HL7v2 XML format
        version: HL7 version string (must be in SUPPORTED_VERSIONS)

    Raises:
        XmlValidationError: If validation fails, version is unsupported, or XML conversion fails
    """
    _check_version_supported(version)

    try:
        er7_string = xml_to_er7(xml_string)
    except ValueError as e:
        raise XmlValidationError(f"Failed to convert XML to ER7: {e}") from e

    validate_er7_with_standard(er7_string, version)
