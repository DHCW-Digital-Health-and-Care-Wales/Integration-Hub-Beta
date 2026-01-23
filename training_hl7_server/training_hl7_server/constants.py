"""HL7 constants for the training server."""


class Hl7Constants:
    # HL7 Field Separator - separates fields within a segment
    FIELD_SEPARATOR = "|"

    # HL7 Encoding Characters - define how components and repetitions are separated
    ENCODING_CHARACTERS = "^~\\&"

    # Processing ID - indicates whether this is Production, Training, or Debugging
    # P = Production, T = Training, D = Debugging
    PROCESSING_ID_PRODUCTION = "P"

    # ACK Message Type - the message type for acknowledgment messages
    ACK_MESSAGE_TYPE = "ACK"

    # ACK Codes - indicate the result of message processing
    ACK_CODE_ACCEPT = "AA"
    ACK_CODE_ERROR = "AE"
    ACK_CODE_REJECT = "AR"
