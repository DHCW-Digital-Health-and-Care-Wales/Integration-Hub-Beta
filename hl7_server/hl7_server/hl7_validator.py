from hl7apy.core import Message


class ValidationException(Exception):
    pass


class HL7Validator:
    def __init__(self, hl7_version: str | None = None, sending_app: str | None = None) -> None:
        self.hl7_version = hl7_version or None
        self.sending_app = sending_app or None

    def validate(self, message: Message) -> None:
        if self.hl7_version:
            message_version: str = message.msh.msh_12.value
            if self.hl7_version != message_version:
                raise ValidationException("Message has wrong version")
            # TODO logger/ audit

        if self.sending_app:
            message_sending_app: str = message.msh.msh_3.value
            if self.sending_app != message_sending_app:
                raise ValidationException("Message has wrong version")
