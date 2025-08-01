from typing import Optional


def transform_date_of_death(date_of_death: Optional[str]) -> str:
    if not date_of_death or not date_of_death.strip():
        return ""

    normalized_value = date_of_death.strip().upper()

    if normalized_value == "RESURREC":
        return '""'

    return date_of_death.strip()
