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
    # These codes are returned in the MSA-1 field of ACK messages
    #
    # AA (Application Accept):
    #   The message was received and successfully processed. This is the
    #   "happy path" response that indicates everything went well.
    #
    # AE (Application Error):
    #   The message was received but failed validation. This indicates a
    #   problem with the message content (e.g., wrong HL7 version, invalid
    #   data format, business rule violation). The sender should fix the
    #   message and potentially resend it.
    #
    # AR (Application Reject):
    #   The message could not be processed due to a system error. This
    #   indicates a problem with the receiving system rather than the
    #   message itself (e.g., database unavailable, queue full). The
    #   sender may retry sending the same message later.
    ACK_CODE_ACCEPT = "AA"
    ACK_CODE_ERROR = "AE"
    ACK_CODE_REJECT = "AR"
