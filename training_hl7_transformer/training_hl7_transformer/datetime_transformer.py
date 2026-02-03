from datetime import datetime


def transform_datetime_to_readable(dt_str: str) -> str | None:
    """
    Convert a datetime string from 'YYYYMMDDHHMMSS' to 'YYYY-MM-DD HH:MM:SS'.

    Args:
        dt_str (str): Datetime string in 'YYYYMMDDHHMMSS' format.

    Returns:
        str: Datetime string in 'YYYY-MM-DD HH:MM:SS' format.

    Raises:
        ValueError: If the input format is invalid.
    """

    print("Transforming datetime string:", dt_str)

    try:
        if dt_str is None or dt_str.strip() == "":
            print("Received empty datetime string to transform.")
            return None

        if len(dt_str) != 14 or not dt_str.isdigit():
            print(f"Invalid datetime format received: {dt_str}")
            raise ValueError(f"✗ Invalid datetime format: {dt_str}")

        dt_str_parsed = datetime.strptime(dt_str, "%Y%m%d%H%M%S")

        return dt_str_parsed.strftime("%Y-%m-%d %H:%M:%S")

    except ValueError as e:
        print(f"Error transforming datetime string '{dt_str}': {e}")
        raise ValueError(f"✗ Error transforming datetime '{dt_str}': {e}")

