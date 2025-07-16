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

        if self.sending_app:
            message_sending_app: str = message.msh.msh_3.value
            allowed_sending_apps = [app.strip() for app in self.sending_app.split(",")]
            if message_sending_app not in allowed_sending_apps:
                raise ValidationException(
                    f"Message sending application '{message_sending_app}' is not in allowed authority codes."
                )
