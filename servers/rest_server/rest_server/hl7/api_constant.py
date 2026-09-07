class ApiConstants:
    # ACK message codes
    ACK_MESSAGE_TYPE_FORMAT = "ACK"
    ACK_CODE_ACCEPT = "AA"  # Application Accept
    ACK_CODE_ERROR = "AE"  # Application Error
    ACK_CODE_REJECT = "AR"  # Application Reject

    # ACK MSH fields — the Integration Hub identifies itself as the acknowledging application.
    ACK_SENDING_APPLICATION = "DHCW"
    ACK_SENDING_FACILITY = "cymru.nhs.uk"

    # HL7 delimiters used when building ACK/NACK strings.
    FIELD_SEPARATOR = "|"
    ENCODING_CHARACTERS = "^~\\&"
    PROCESSING_ID_PRODUCTION = "P"

    # Segment separator used in the ACK/NACK returned to the caller.
    SEGMENT_SEPARATOR = "\r\n"

    # Fallback HL7 version used when the inbound message cannot be parsed.
    DEFAULT_HL7_VERSION = "2.5.1"

    # Maximum length (characters) for a generated message control ID (MSH.10).
    GENERATED_CONTROL_ID_MAX_LENGTH = 20

    # Default MSA text for a successfully received message.
    SUCCESS_MESSAGE = "Message received successfully."

    # API metadata (surfaced on the health/status endpoints).
    REVISION = "0"
    VERSION = "1.0"
    APPLICATION_NAME = "HL7 Message Receiver"
