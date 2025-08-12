from typing import Any


def _get_field_text(field: Any) -> str:
    try:
        return field.to_er7().strip()  # type: ignore[attr-defined]
    except Exception:
        value = getattr(field, "value", None)
        return (value or "").strip()


