"""HL7 constants for the training server."""


class Hl7Constants:
    """Constants used in HL7 message processing."""

    # HL7 Field Separator - separates fields within a segment
    # Example: MSH|^~\&|SENDING_APP|...
    #             ↑ This is the field separator
    FIELD_SEPARATOR = "|"

    # HL7 Encoding Characters - define how components and repetitions are separated
    # ^ = Component separator (separates parts within a field)
    # ~ = Repetition separator (separates repeated fields)
    # \ = Escape character (escapes special characters)
    # & = Sub-component separator (separates sub-parts of components)
    ENCODING_CHARACTERS = "^~\\&"

    # Processing ID - indicates whether this is Production, Training, or Debugging
    # P = Production, T = Training, D = Debugging
    PROCESSING_ID_PRODUCTION = "P"

    # ACK Message Type - the message type for acknowledgment messages
    ACK_MESSAGE_TYPE = "ACK"

    # ACK Codes - indicate the result of message processing
    ACK_CODE_ACCEPT = "AA"  # Application Accept - message was successfully processed
    ACK_CODE_ERROR = "AE"  # Application Error - message had validation errors
    ACK_CODE_REJECT = "AR"  # Application Reject - message was rejected
