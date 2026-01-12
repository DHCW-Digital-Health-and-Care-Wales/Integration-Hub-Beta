class Hl7Constants:
    # HL7 Delimiters
    FIELD_SEPARATOR = "|"
    ENCODING_CHARACTERS = "^~\\&"
    PROCESSING_ID_PRODUCTION = "P"

    # ACK message type template
    ACK_MESSAGE_TYPE = "ACK"
    ACK_CODE_ACCEPT = "AA"  # Application Accep
    ACK_CODE_ERROR = "AE"   # Application Error
