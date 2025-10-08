from hl7_validation.utils.message_utils import extract_message_trigger
from hl7apy.core import Message

from hl7_server.custom_validation.phw_validation import _validate_pid7_date_of_birth
from hl7_server.exceptions.validation_exception import ValidationException


class HL7Validator:
    def __init__(
        self, hl7_version: str | None = None, sending_app: str | None = None, flow_name: str | None = None
    ) -> None:
        self.hl7_version = hl7_version or None
        self.sending_app = sending_app or None
        self.flow_name = flow_name or None

    def validate(self, message: Message) -> None:
        # Common validations for all flows
        self._validate_hl7_version(message)
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
        if self.flow_name == "phw":
            self._validate_phw_specific_fields(message)
        if self.flow_name == "mpi":
            self._validate_mpi_outbound_specific_fields(message)

    def _validate_phw_specific_fields(self, message: Message) -> None:
        _validate_pid7_date_of_birth(message)

    def _validate_mpi_outbound_specific_fields(self, message: Message) -> None:
        ALLOWED_MPI_MESSAGE_TYPES: set[str] = {"A28", "A31", "A40"}

        message_type = extract_message_trigger(message)
        if not message_type:
            raise ValidationException("MSH.9.2 (MessageType) is missing from the message")

        if message_type.upper() not in ALLOWED_MPI_MESSAGE_TYPES:
            raise ValidationException(f"Unsupported message type '{message_type.upper()}' for MPI outbound flow")

        # TODO use utils library (to be published) to extract pid.pid_2.cx_4.hd_1
        update_source = "100"
        if not update_source:
            raise ValidationException("PID.2.4.1 (UpdateSource) is missing from the MPI outbound message")
