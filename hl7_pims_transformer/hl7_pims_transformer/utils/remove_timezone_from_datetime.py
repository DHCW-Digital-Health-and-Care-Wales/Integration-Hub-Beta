from typing import Optional


def remove_timezone_from_datetime(datetime_value: Optional[str]) -> str:
    if not datetime_value or not datetime_value.strip():
        return ""

    # remove timezone by taking everything before the '+' sign
    datetime_without_timezone = datetime_value.split('+')[0].strip()

    datetime_length = len(datetime_without_timezone)

    # validate the resulting format
    if datetime_length not in [8, 14] or not datetime_without_timezone.isdigit():
        raise ValueError(
            f"Invalid datetime format after timezone removal: '{datetime_without_timezone}'. "
            f"Expected format: YYYYMMDD (8 digits) or YYYYMMDDHHMMSS (14 digits)"
        )

    return datetime_without_timezone
