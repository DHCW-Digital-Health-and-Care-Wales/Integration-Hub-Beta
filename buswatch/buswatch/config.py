"""Runtime configuration for BusWatch."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONNECTION_STRING = (
    # Emulator default uses localhost because this file is also used for
    # non-container local runs. In Docker, this is typically overridden
    # with Endpoint=sb://sb-emulator via environment variables.
    "Endpoint=sb://localhost;"
    "SharedAccessKeyName=RootManageSharedAccessKey;"
    "SharedAccessKey=SAS_KEY_VALUE;"
    "UseDevelopmentEmulator=true;"
)


@dataclass(frozen=True)
class Settings:
    """Typed runtime settings used by the web application.

    Keeping settings in a frozen dataclass provides:
    - One place to document supported runtime knobs.
    - A clear contract for downstream components.
    - Immutability, so settings cannot accidentally drift at runtime.
    """

    servicebus_connection_string: str
    queue_names: list[str]
    peek_count: int
    detail_search_limit: int


# Local fallback config used when environment variables are not provided.
# Path resolves to buswatch/config.ini when running from source tree.
CONFIG_FILE_PATH = Path(__file__).resolve().parents[1] / "config.ini"



def _parse_queue_names(raw_value: str) -> list[str]:
    """Parse a comma-separated queue list into clean queue names.

    The input may contain extra spaces and trailing commas, so this helper
    normalizes values and drops blank entries.
    """
    return [name.strip() for name in raw_value.split(",") if name.strip()]


def _load_config_file_values() -> dict[str, str]:
    """Load key=value settings from local config.ini if present.

    The parser is intentionally lightweight and tolerant:
    - Ignores comments and blank lines.
    - Ignores malformed lines without '='.
    - Uses first '=' as delimiter so values can contain '='.
    """
    if not CONFIG_FILE_PATH.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in CONFIG_FILE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def _read_setting(name: str, default: str, config_values: dict[str, str]) -> str:
    """Read a setting with precedence: env var -> config.ini -> default.

    Environment variables are intentionally highest priority so container or
    CI environments can override committed defaults without editing files.
    """
    return os.getenv(name, config_values.get(name, default))



def get_settings() -> Settings:
    """Build and validate the settings object used by the app.

    Validation here is lightweight (mainly int conversion) so startup fails
    early if configuration values are invalid.
    """
    config_values = _load_config_file_values()

    queue_names_raw = _read_setting("BUSWATCH_QUEUE_NAMES", "", config_values)
    queue_names = _parse_queue_names(queue_names_raw)

    # Convert numeric settings once at startup to avoid repeated parsing.
    peek_count = int(_read_setting("BUSWATCH_PEEK_COUNT", "25", config_values))
    detail_search_limit = int(_read_setting("BUSWATCH_DETAIL_SEARCH_LIMIT", "250", config_values))

    return Settings(
        servicebus_connection_string=_read_setting(
            "SERVICEBUS_CONNECTION_STRING", DEFAULT_CONNECTION_STRING, config_values
        ),
        queue_names=queue_names,
        peek_count=peek_count,
        detail_search_limit=detail_search_limit,
    )
