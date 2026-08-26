from hl7apy.core import Message

from rest_server.hl7.custom_validation.mpi_outbound_validation import validate_mpi_outbound_specific_fields
from rest_server.hl7.custom_validation.risp_validation import validate_risp_message
from rest_server.hl7.exceptions.validation_exception import ValidationException

__all__ = ["HL7Validator", "ValidationException"]


class HL7Validator:
    """Integration Hub message validation (version, sending application, flow-specific rules).

    Mirrors the ``hl7_server`` validator so the REST receiver enforces the same
    rules as the MLLP server.
    """

    def __init__(
        self, hl7_version: str | None = None, sending_app: str | None = None, flow_name: str | None = None
    ) -> None:
        self.hl7_version = hl7_version or None
        self.sending_app = sending_app or None
        self.flow_name = flow_name or None

    def validate(self, message: Message) -> None:
        # Common validations for all flows
        self._validate_hl7_version(message)

        # The 'risp' flow accepts several message types, each with its own required sending
        # facility (MSH.3) range (see validate_risp_message) — the single-value SENDING_APP check
        # below doesn't fit that shape, so it is skipped in favour of the flow-specific rule.
        if self.flow_name != "risp":
            self._validate_sending_app(message)

        # Flow-specific validation if needed
        if self.flow_name:
            self._validate_flow_specific(message)

    def _validate_hl7_version(self, message: Message) -> None:
        if self.hl7_version:
            message_version: str = message.msh.msh_12.value
            if self.hl7_version != message_version:
                raise ValidationException("Message has wrong version")

    def _validate_sending_app(self, message: Message) -> None:
        if self.sending_app:
            message_sending_app: str = message.msh.msh_3.value
            allowed_sending_apps = [app.strip() for app in self.sending_app.split(",")]
            if message_sending_app not in allowed_sending_apps:
                raise ValidationException(
                    f"Message sending application '{message_sending_app}' is not in allowed authority codes."
                )

    def _validate_flow_specific(self, message: Message) -> None:
        if self.flow_name == "mpi":
            validate_mpi_outbound_specific_fields(message)
        if self.flow_name == "risp":
            validate_risp_message(message)
