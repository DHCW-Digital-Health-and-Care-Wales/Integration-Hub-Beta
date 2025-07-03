from datetime import datetime


def transform_datetime(date_time: str) -> str:
    required_format = "%Y%m%d%H%M%S"
    try:
        # Check if already in required format
        datetime.strptime(date_time, required_format)
        return date_time
    except ValueError:
        dt = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
        return dt.strftime(required_format)
