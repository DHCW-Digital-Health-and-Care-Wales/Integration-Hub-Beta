"""Shared Azure Communication Services (ACS) email sending.

Single source of truth used by Alarm 1 / Alarm 2 / Alarm 3 (and any future
callers) to send alert emails. Responsible for:

1. Resolving the ACS connection string — preferring Key Vault (read via the
   container's managed identity, ``AZURE_CLIENT_ID``) with an in-memory TTL
   cache, and falling back to the ``ACS_CONNECTION_STRING`` env var for local
   development where Key Vault may not be reachable/configured.
2. Sending the email via the ACS ``EmailClient``.

All failures are caught and logged — email delivery must never raise and
break an alarm evaluation cycle.
"""

from __future__ import annotations

import logging
import time
from threading import Lock

from dashboard import config
from dashboard.services.credentials import get_azure_credential

log = logging.getLogger(__name__)

_secret_cache: str | None = None
_secret_cache_expiry: float = 0.0
_cache_lock = Lock()


def _fetch_from_key_vault() -> str | None:
    """Fetch the ACS connection string secret from Key Vault. Returns None on failure."""
    try:
        from azure.keyvault.secrets import SecretClient  # noqa: PLC0415

        client = SecretClient(vault_url=config.AZURE_KEY_VAULT_URL, credential=get_azure_credential())
        secret = client.get_secret(config.ACS_EMAIL_SECRET_NAME)
        return secret.value
    except Exception as exc:
        log.error("Failed to fetch ACS connection string from Key Vault: %s", exc, exc_info=True)
        return None


def get_acs_connection_string() -> str:
    """Resolve the ACS connection string, preferring a cached Key Vault fetch.

    Falls back to ``config.ACS_CONNECTION_STRING`` (local-dev env var override) when
    ``AZURE_KEY_VAULT_URL`` is not configured, or if the Key Vault fetch fails.
    """
    global _secret_cache, _secret_cache_expiry  # noqa: PLW0603

    if not config.AZURE_KEY_VAULT_URL:
        return config.ACS_CONNECTION_STRING

    with _cache_lock:
        now = time.monotonic()
        if _secret_cache and now < _secret_cache_expiry:
            return _secret_cache

        fetched = _fetch_from_key_vault()
        if fetched:
            _secret_cache = fetched
            _secret_cache_expiry = now + config.ACS_SECRET_CACHE_TTL
            return fetched

    # Key Vault fetch failed — fall back to env var (may be empty).
    log.warning("Falling back to ACS_CONNECTION_STRING env var after Key Vault fetch failure")
    return config.ACS_CONNECTION_STRING


def _retry_after_seconds(exc: Exception, attempt: int) -> float:
    """Determine how long to wait before retrying after a throttling error.

    Prefers the server-provided ``Retry-After`` header (seconds) when present,
    falling back to exponential backoff based on ``ALERT_EMAIL_RETRY_BACKOFF_SECONDS``.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    if headers:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                pass

    return config.ALERT_EMAIL_RETRY_BACKOFF_SECONDS * (2**attempt)


def _is_throttling_error(exc: Exception) -> bool:
    """Return True if the exception represents an ACS 429 TooManyRequests response."""
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 429


def send_alert_email(subject: str, html_body: str) -> bool:
    """Send an HTML alert email via Azure Communication Services.

    Returns True on success, False otherwise (never raises). Callers should
    treat a False return as "email not sent" and continue — alarm evaluation
    must not be blocked by email delivery issues.

    Retries with backoff on ACS 429 (TooManyRequests) responses, since the ACS
    Email sandbox domain has a low, fixed per-minute/per-hour send quota that
    multiple alarms firing in the same evaluation cycle can easily exceed.
    """
    if not config.ALERT_EMAIL_ENABLED:
        return False

    connection_string = get_acs_connection_string()
    if not connection_string or not config.ALERT_EMAIL_TO or not config.ALERT_EMAIL_FROM:
        log.warning("Alert email enabled but ACS connection string / ALERT_EMAIL_TO / ALERT_EMAIL_FROM not set")
        return False

    try:
        from azure.communication.email import EmailClient  # noqa: PLC0415

        client = EmailClient.from_connection_string(connection_string)
        message = {
            "senderAddress": config.ALERT_EMAIL_FROM,
            "recipients": {"to": [{"address": config.ALERT_EMAIL_TO}]},
            "content": {"subject": subject, "html": html_body},
        }

        max_retries = config.ALERT_EMAIL_MAX_RETRIES
        for attempt in range(max_retries + 1):
            try:
                poller = client.begin_send(message)
                poller.result()
                log.info("Alert email sent to %s: %s", config.ALERT_EMAIL_TO, subject)
                return True
            except Exception as exc:
                if _is_throttling_error(exc) and attempt < max_retries:
                    wait_seconds = _retry_after_seconds(exc, attempt)
                    log.warning(
                        "ACS throttled alert email (%s), retrying in %.1fs (attempt %d/%d): %s",
                        subject,
                        wait_seconds,
                        attempt + 1,
                        max_retries,
                        exc,
                    )
                    time.sleep(wait_seconds)
                    continue
                raise
    except Exception as exc:
        log.error("Failed to send alert email (%s): %s", subject, exc, exc_info=True)
        return False

    return False
