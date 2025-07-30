from datetime import datetime
from typing import Optional


def transform_datetime(date_time: str) -> str:
    required_format = "%Y%m%d%H%M%S"
    try:
        # Check if already in required format
        datetime.strptime(date_time, required_format)
        return date_time
    except ValueError:
        dt = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
        return dt.strftime(required_format)

def transform_date_of_death(date_of_death: Optional[str]) -> str:
    if not date_of_death or not date_of_death.strip():
        return ""
    
    normalized_value = date_of_death.strip().upper()
    
    if normalized_value == "RESURREC":
        return '""'
    
    return date_of_death.strip()