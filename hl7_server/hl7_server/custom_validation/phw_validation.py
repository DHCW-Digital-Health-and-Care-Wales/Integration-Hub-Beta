from datetime import datetime

from hl7apy.core import Message

from hl7_server.exceptions.validation_exception import ValidationException


def _validate_pid7_date_of_birth(message: Message) -> None:
    if not hasattr(message, "pid"):
        raise ValidationException("PID.7 (Date of birth) is required for PHW.")

    pid_7 = getattr(message.pid, "pid_7", None)
    dob = str(getattr(pid_7, "value", "")).strip() if pid_7 is not None else ""

    if not dob:
        raise ValidationException("PID.7 (Date of birth) is required for PHW.")
    # Only the yyyyMMdd format is accepted for PID.7 (Date of birth) in the PHW flow
    if not dob.isdigit() or len(dob) != 8:
        raise ValidationException("PID.7 (Date of birth) must be a valid date in YYYYMMDD format for PHW.")

    try:
        birthdate = datetime.strptime(dob, "%Y%m%d")
        if birthdate.year < 1800:
            raise ValidationException("PID.7 (Date of birth) - year of birth must be 1800 or later for PHW.")
    except ValueError:
        raise ValidationException("PID.7 (Date of birth) must be a valid date in YYYYMMDD format for PHW.")
