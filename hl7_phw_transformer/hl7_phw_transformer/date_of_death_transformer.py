from typing import Optional


def transform_date_of_death(date_of_death: Optional[str]) -> str:
    if not date_of_death or not date_of_death.strip():
        return '""'

    normalized_value = date_of_death.strip()
    if len(normalized_value) <= 6:
        return '""'

    # PID.29 is expected without timezone metadata for MPI compatibility.
    return normalized_value.split("+", 1)[0].strip()
