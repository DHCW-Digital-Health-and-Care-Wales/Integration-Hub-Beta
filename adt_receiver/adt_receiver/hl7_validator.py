from hl7apy.core import Message

from adt_receiver.exceptions.validation_exception import ValidationException

ADT_MESSAGE_CODE = "ADT"


class HL7Validator:
    def __init__(
        self,
        hl7_version: str | None = None,
        sending_app: str | None = None,
        message_type: str | None = None,
    ) -> None:
        self.hl7_version = hl7_version or None
        self.sending_app = sending_app or None
        self.message_type = message_type or None

    def validate(self, message: Message) -> None:
        self._validate_hl7_version(message)
        self._validate_sending_app(message)
        self._validate_adt_message_type(message)
        self._validate_trigger_event(message)

    def _validate_hl7_version(self, message: Message) -> None:
        if self.hl7_version:
            message_version: str = message.msh.msh_12.value
            allowed_versions = [v.strip() for v in self.hl7_version.split(",")]
            if message_version not in allowed_versions:
                raise ValidationException(
                    f"Message has wrong HL7 version: expected one of {allowed_versions}, got {message_version}"
                )

    def _validate_sending_app(self, message: Message) -> None:
        if self.sending_app:
            message_sending_app: str = message.msh.msh_3.value
            allowed_sending_apps = [app.strip() for app in self.sending_app.split(",")]
            if message_sending_app not in allowed_sending_apps:
                raise ValidationException(
                    f"Message sending application '{message_sending_app}' is not in allowed authority codes."
                )

    def _validate_adt_message_type(self, message: Message) -> None:
        msg_code: str = message.msh.msh_9.msh_9_1.value
        if msg_code != ADT_MESSAGE_CODE:
            raise ValidationException(f"Only ADT message types are accepted, received: {msg_code}")

    def _validate_trigger_event(self, message: Message) -> None:
        if self.message_type:
            trigger_event: str = message.msh.msh_9.msh_9_2.value
            allowed_trigger_events = [t.strip() for t in self.message_type.split(",")]
            if trigger_event not in allowed_trigger_events:
                raise ValidationException(
                    f"ADT trigger event '{trigger_event}' is not in allowed list: {allowed_trigger_events}"
                )
