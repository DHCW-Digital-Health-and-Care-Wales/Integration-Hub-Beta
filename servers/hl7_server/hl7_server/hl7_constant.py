class Hl7Constants:
    # HL7 Delimiters
    FIELD_SEPARATOR = "|"
    ENCODING_CHARACTERS = "^~\\&"
    PROCESSING_ID_PRODUCTION = "P"

    # ACK message type template
    ACK_MESSAGE_TYPE_FORMAT = "ACK"
    ACK_CODE_ACCEPT = "AA"  # Application Accept
    ACK_CODE_REJECT = "AR"  # Application Reject - used for validation failures
    ACK_CODE_ERROR = "AE"  # Application Error - used for parsing/unexpected processing failures

    # Fallback HL7 version used in a NACK when no inbound message could be parsed to recover one.
    DEFAULT_HL7_VERSION = "2.5"

    # Maximum length (characters) for a generated message control ID (MSH.10).
    GENERATED_CONTROL_ID_MAX_LENGTH = 20

    # Maximum length (characters) applied to NACK reason text (MSA.3) - matches the HL7 ST
    # datatype's 199 character limit so downstream systems using strict parsing can still consume it.
    MAX_NACK_REASON_LENGTH = 199
