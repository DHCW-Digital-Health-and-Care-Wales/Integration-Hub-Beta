class DeadLetterMessage(Exception):
    """Signal raised by a message processor to indicate that the current message is
    non-recoverable and must be dead-lettered immediately, bypassing the normal
    abandon/retry path (e.g. a non-recoverable HL7 NACK such as MSA-1 = AR).

    ``MessageReceiverClient`` (and subclasses such as ``SubscriptionReceiverClient``)
    catch this specifically in their per-message processing loop and call the
    Service Bus receiver's ``dead_letter_message`` with the supplied reason/description,
    instead of abandoning the message for redelivery.
    """

    def __init__(self, reason: str, description: str):
        super().__init__(description)
        self.reason = reason
        self.description = description
