from datetime import datetime

from hl7apy.core import Message


class ValidationException(Exception):
    pass


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

    def _validate_phw_specific_fields(self, message: Message) -> None:
        self._validate_pid7_date_of_birth(message)

    def _validate_pid7_date_of_birth(self, message: Message) -> None:
        if not hasattr(message, "pid"):
            raise ValidationException("PID.7 (Date of birth) is required for PHW.")

        pid_7 = getattr(message.pid, "pid_7", None)
        dob = str(getattr(pid_7, "value", "")).strip() if pid_7 is not None else ""

        if not dob:
            raise ValidationException("PID.7 (Date of birth) is required for PHW.")
        # expecting only YYYYMMDD
        if not dob.isdigit() or len(dob) != 8:
            raise ValidationException("PID.7 (Date of birth) must be a valid date in YYYYMMDD format for PHW.")

        try:
            birthdate = datetime.strptime(dob, "%Y%m%d")
            if birthdate.year < 1800:
                raise ValidationException("PID.7 (Date of birth) - year of birth must be 1800 or later for PHW.")
        except ValueError:
            # to handle the edge case of "00000000"
            raise ValidationException("PID.7 (Date of birth) must be a valid date in YYYYMMDD format for PHW.")
