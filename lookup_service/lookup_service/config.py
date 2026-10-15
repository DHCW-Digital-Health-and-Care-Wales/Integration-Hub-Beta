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
LOCAL_ENVIRONMENT = "LOCAL"
LOCAL_COSMOS_HOSTS = ("localhost", "127.0.0.1", "cosmos-emulator")


@dataclass(frozen=True)
class Settings:
    seed_dir: Path
    environment: str
    host: str
    port: int
    log_level: str
    cosmos_endpoint: str | None = None
    cosmos_key: str | None = None
    cosmos_database: str = "integration-hub"
    cosmos_disable_ssl_verify: bool = False
    rows_container: str = "lookup-rows"
    config_container: str = "lookup-config"
    default_ttl_seconds: int = 300
    cache_max_entries: int = 10_000
    max_upload_mb: int = 50
    upload_concurrency: int = 32
    auth_tenant_id: str | None = None
    auth_audience: str | None = None
    # Only honoured when environment == LOCAL (see validate()).
    auth_disabled: bool = False

    @property
    def swagger_enabled(self) -> bool:
        return self.environment in SWAGGER_ENABLED_ENVIRONMENTS

    @property
    def is_local(self) -> bool:
        return self.environment == LOCAL_ENVIRONMENT

    @property
    def auth_enabled(self) -> bool:
        return not self.auth_disabled

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @staticmethod
    def from_env() -> Settings:
        settings = Settings(
            seed_dir=Path(_read_env("LOOKUP_SEED_DIR") or DEFAULT_SEED_DIR),
            environment=(_read_env("ENVIRONMENT") or DEFAULT_ENVIRONMENT).upper(),
            host=_read_env("HOST") or DEFAULT_HOST,
            port=_read_int_env("PORT", DEFAULT_PORT),
            log_level=(_read_env("LOG_LEVEL") or "INFO").upper(),
            cosmos_endpoint=_read_env("COSMOS_ENDPOINT"),
            cosmos_key=_read_env("COSMOS_KEY"),
            cosmos_database=_read_env("COSMOS_DATABASE") or "integration-hub",
            cosmos_disable_ssl_verify=(_read_env("COSMOS_DISABLE_SSL_VERIFY") or "false").lower() == "true",
            rows_container=_read_env("LOOKUP_ROWS_CONTAINER") or "lookup-rows",
            config_container=_read_env("LOOKUP_CONFIG_CONTAINER") or "lookup-config",
            default_ttl_seconds=_read_int_env("LOOKUP_DEFAULT_TTL_SECONDS", 300, minimum=1),
            cache_max_entries=_read_int_env("LOOKUP_CACHE_MAX_ENTRIES", 10_000, minimum=1),
            max_upload_mb=_read_int_env("LOOKUP_MAX_UPLOAD_MB", 50, minimum=1),
            upload_concurrency=_read_int_env("LOOKUP_UPLOAD_CONCURRENCY", 32, minimum=1),
            auth_tenant_id=_read_env("LOOKUP_AUTH_TENANT_ID"),
            auth_audience=_read_env("LOOKUP_AUTH_AUDIENCE"),
            auth_disabled=_read_bool_env("LOOKUP_AUTH_DISABLED"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.auth_disabled and not self.is_local:
            raise RuntimeError(f"LOOKUP_AUTH_DISABLED=true is only allowed when ENVIRONMENT={LOCAL_ENVIRONMENT}")
        # Fail closed: never serve unauthenticated because configuration is missing.
        if self.auth_enabled and not (self.auth_tenant_id and self.auth_audience):
            hint = " (set LOOKUP_AUTH_DISABLED=true for local development)" if self.is_local else ""
            raise RuntimeError(
                "Authentication is not configured: set LOOKUP_AUTH_TENANT_ID and LOOKUP_AUTH_AUDIENCE" + hint
            )
        if self.cosmos_disable_ssl_verify and self.cosmos_endpoint:
            endpoint = self.cosmos_endpoint.lower()
            # The emulator's certificate is self-signed; never disable verification for a real account.
            if not any(host in endpoint for host in LOCAL_COSMOS_HOSTS):
                raise RuntimeError("COSMOS_DISABLE_SSL_VERIFY is only allowed for a local Cosmos emulator endpoint")


def _read_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _read_bool_env(name: str) -> bool:
    value = _read_env(name)
    if value is None or value.lower() in {"false", "0"}:
        return False
    if value.lower() in {"true", "1"}:
        return True
    raise RuntimeError(f"Environment variable {name} must be true or false")


def _read_int_env(name: str, default: int, minimum: int | None = None) -> int:
    value = _read_env(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer, got {value!r}") from exc
    if minimum is not None and parsed < minimum:
        raise RuntimeError(f"Environment variable {name} must be >= {minimum}, got {parsed}")
    return parsed
