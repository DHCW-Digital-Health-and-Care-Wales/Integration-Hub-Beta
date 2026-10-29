from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "0.0.0.0"  # nosec B104 - bind all interfaces inside the container
DEFAULT_PORT = 8080
DEFAULT_ENVIRONMENT = "DEV"

# Environments in which the interactive Swagger / OpenAPI UI is exposed.
SWAGGER_ENABLED_ENVIRONMENTS = frozenset({"LOCAL", "DEV", "SIT"})
LOCAL_ENVIRONMENT = "LOCAL"
# Where LOOKUP_AUTH_DISABLED may be set: LOCAL, plus DEV/TST for the unauthenticated trial (plan Phase 1.25).
# Outside LOCAL it also needs LOOKUP_AUTH_DISABLED_ACK, so one stray flag in tfvars can't open the service.
AUTH_DISABLE_ALLOWED_ENVIRONMENTS = (LOCAL_ENVIRONMENT, "DEV", "TST")
AUTH_DISABLED_ACK_VALUE = "I_UNDERSTAND_LOOKUP_IS_UNAUTHENTICATED"
LOCAL_COSMOS_HOSTS = ("localhost", "127.0.0.1", "cosmos-emulator")


@dataclass(frozen=True)
class Settings:
    # None (LOOKUP_SEED_DIR unset, the deployed default): nothing is seeded at startup and, without Cosmos,
    # no tables are served. Only local Compose sets it, to load local/lookup-seed.
    seed_dir: Path | None
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
    # Restricted by validate() to AUTH_DISABLE_ALLOWED_ENVIRONMENTS, with the acknowledgement outside LOCAL.
    auth_disabled: bool = False
    auth_disabled_ack: str | None = None

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
    def unauthenticated_deployment(self) -> bool:
        """Auth is off in a deployed environment (DEV/TST trial), not just on a developer machine."""
        return self.auth_disabled and not self.is_local

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @staticmethod
    def from_env() -> Settings:
        seed_dir = _read_env("LOOKUP_SEED_DIR")
        settings = Settings(
            seed_dir=Path(seed_dir) if seed_dir else None,
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
            auth_disabled_ack=_read_env("LOOKUP_AUTH_DISABLED_ACK"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.auth_disabled:
            self._validate_auth_disabled()
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

    def _validate_auth_disabled(self) -> None:
        if self.environment not in AUTH_DISABLE_ALLOWED_ENVIRONMENTS:
            allowed = ", ".join(AUTH_DISABLE_ALLOWED_ENVIRONMENTS)
            raise RuntimeError(f"LOOKUP_AUTH_DISABLED=true is only allowed when ENVIRONMENT is one of {allowed}")
        if not self.is_local and self.auth_disabled_ack != AUTH_DISABLED_ACK_VALUE:
            raise RuntimeError(
                f"LOOKUP_AUTH_DISABLED=true in {self.environment} also needs "
                f"LOOKUP_AUTH_DISABLED_ACK={AUTH_DISABLED_ACK_VALUE}"
            )


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
