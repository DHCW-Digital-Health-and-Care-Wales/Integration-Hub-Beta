class Hl7Constants:
    # HL7 Delimiters
    FIELD_SEPARATOR = "|"
    ENCODING_CHARACTERS = "^~\\&"
    PROCESSING_ID_PRODUCTION = "P"

    # ACK message type
    ACK_MESSAGE_TYPE_FORMAT = "ACK"
    ACK_CODE_ACCEPT = "AA"   # Application Accept
    NACK_CODE_ERROR = "AE"   # Application Error
    NACK_CODE_REJECT = "AR"  # Application Reject
