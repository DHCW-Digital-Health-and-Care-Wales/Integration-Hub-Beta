"""Authentication for Promptly requests.

The WPAS-Promptly IG allows exactly one mechanism per environment:
  - API key in ``X-API-Key`` (currently active)
  - OAuth 2.0 client-credentials bearer token (target mechanism); the token replaces the API key.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Protocol

import requests

from fhir_sender.errors import AuthorizationDeliveryError, TransientDeliveryError

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_LIFETIME_SECONDS = 3600
TOKEN_REFRESH_MARGIN_SECONDS = 60


class AuthProvider(Protocol):
    def headers(self) -> dict[str, str]:
        """Return the authentication headers for the next request."""
        ...

    def invalidate(self) -> bool:
        """Discard cached credentials after a 401; return True if a retry with fresh credentials is worthwhile."""
        ...


class ApiKeyAuth:
    def __init__(self, api_key: str) -> None:
        if not api_key.strip():
            raise ValueError("API key must not be empty")
        self._api_key = api_key

    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key}

    def invalidate(self) -> bool:
        return False


class OAuth2ClientCredentialsAuth:
    """Fetches a bearer token once and reuses it until shortly before it expires."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        timeout_seconds: int = 30,
        session: requests.Session | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        self._monotonic = monotonic
        self._token: str | None = None
        self._expires_at = 0.0

    def headers(self) -> dict[str, str]:
        if self._token is None or self._monotonic() >= self._expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
            self._fetch_token()
        return {"Authorization": f"Bearer {self._token}"}

    def invalidate(self) -> bool:
        self._token = None
        return True

    def _fetch_token(self) -> None:
        try:
            response = self._session.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": self._scope,
                },
                timeout=self._timeout_seconds,
                allow_redirects=False,
            )
        except requests.exceptions.RequestException as exc:
            raise TransientDeliveryError(f"Token request failed: {exc}") from exc

        if response.status_code in (400, 401, 403):
            raise AuthorizationDeliveryError(response.status_code, "Token endpoint rejected the client credentials")
        if response.status_code != 200:
            raise TransientDeliveryError(f"Token endpoint returned HTTP {response.status_code}")

        try:
            payload = response.json()
            token = payload["access_token"]
            lifetime = float(payload.get("expires_in", DEFAULT_TOKEN_LIFETIME_SECONDS))
        except (ValueError, KeyError, TypeError) as exc:
            raise TransientDeliveryError("Token endpoint returned an unreadable response") from exc

        self._token = token
        self._expires_at = self._monotonic() + lifetime
        logger.info("Obtained OAuth2 access token (valid for %.0fs)", lifetime)
