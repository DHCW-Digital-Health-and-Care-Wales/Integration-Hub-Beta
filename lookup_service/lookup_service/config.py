from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "0.0.0.0"  # nosec B104 - bind all interfaces inside the container
DEFAULT_PORT = 8080
DEFAULT_ENVIRONMENT = "DEV"
DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent / "seed"

# Environments in which the interactive Swagger / OpenAPI UI is exposed.
SWAGGER_ENABLED_ENVIRONMENTS = frozenset({"LOCAL", "DEV", "SIT"})


@dataclass(frozen=True)
class Settings:
    seed_dir: Path
    environment: str
    host: str
    port: int
    log_level: str

    @property
    def swagger_enabled(self) -> bool:
        return self.environment in SWAGGER_ENABLED_ENVIRONMENTS

    @staticmethod
    def from_env() -> Settings:
        return Settings(
            seed_dir=Path(_read_env("LOOKUP_SEED_DIR") or DEFAULT_SEED_DIR),
            environment=(_read_env("ENVIRONMENT") or DEFAULT_ENVIRONMENT).upper(),
            host=_read_env("HOST") or DEFAULT_HOST,
            port=_read_int_env("PORT", DEFAULT_PORT),
            log_level=(_read_env("LOG_LEVEL") or "INFO").upper(),
        )


def _read_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _read_int_env(name: str, default: int) -> int:
    value = _read_env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer, got {value!r}") from exc
