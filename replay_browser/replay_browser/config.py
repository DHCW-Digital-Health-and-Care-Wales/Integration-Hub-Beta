import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    sql_server: str
    sql_database: str
    sql_username: str | None
    sql_password: str | None
    sql_encrypt: str
    sql_trust_server_certificate: str
    page_size: int


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _read_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _parse_page_size(raw: str | None) -> int:
    if not raw:
        return 30
    try:
        page_size = int(raw)
    except ValueError as exc:
        raise ConfigError("MESSAGE_BROWSER_PAGE_SIZE must be an integer") from exc

    if page_size < 1 or page_size > 200:
        raise ConfigError("MESSAGE_BROWSER_PAGE_SIZE must be between 1 and 200")
    return page_size


def load_config() -> AppConfig:
    sql_server = _read_env("SQL_SERVER", "localhost,1433")
    sql_database = _read_env("SQL_DATABASE", "IntegrationHub")
    sql_username = _read_env("SQL_USERNAME", "sa")
    sql_password = _read_env("MSSQL_SA_PASSWORD")
    sql_encrypt = _read_env("SQL_ENCRYPT", "No") or "No"
    sql_trust_server_certificate = _read_env("SQL_TRUST_SERVER_CERTIFICATE", "Yes") or "Yes"
    page_size = _parse_page_size(_read_env("MESSAGE_BROWSER_PAGE_SIZE"))

    if not sql_server:
        raise ConfigError("SQL_SERVER cannot be empty")
    if not sql_database:
        raise ConfigError("SQL_DATABASE cannot be empty")

    username_provided = bool(sql_username)
    password_provided = bool(sql_password)
    if username_provided != password_provided:
        missing = "MSSQL_SA_PASSWORD" if username_provided else "SQL_USERNAME"
        provided = "SQL_USERNAME" if username_provided else "MSSQL_SA_PASSWORD"
        raise ConfigError(f"{missing} must be provided when {provided} is set")

    return AppConfig(
        sql_server=sql_server,
        sql_database=sql_database,
        sql_username=sql_username,
        sql_password=sql_password,
        sql_encrypt=sql_encrypt,
        sql_trust_server_certificate=sql_trust_server_certificate,
        page_size=page_size,
    )
