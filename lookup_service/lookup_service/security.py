"""Authentication, role checks and CSRF protection.

Two callers, two mechanisms:

- The lookup API (`/api/v1/lookup*`) takes an Entra bearer token, validated here against the tenant's JWKS.
- The GUI and admin API sit behind Container Apps Easy Auth, which overwrites the `X-MS-CLIENT-PRINCIPAL*`
  headers; they are only trusted when auth is enabled, i.e. the service is reached through Easy Auth.

Tokens, keys and header contents are never logged.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends, Request
from fastapi.responses import Response

from lookup_service.config import Settings
from lookup_service.errors import (
    BackendUnavailableError,
    CsrfError,
    ForbiddenError,
    UnauthorizedError,
)

logger = logging.getLogger(__name__)

ROLE_READER = "Lookup.Reader"
ROLE_EDITOR = "Lookup.Editor"
ROLE_ADMIN = "Lookup.Admin"
# Each role includes the ones below it.
READER_ROLES = frozenset({ROLE_READER, ROLE_EDITOR, ROLE_ADMIN})
EDITOR_ROLES = frozenset({ROLE_EDITOR, ROLE_ADMIN})

JWKS_URL = "https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
JWKS_TIMEOUT_SECONDS = 5
CLOCK_SKEW_SECONDS = 60

EASY_AUTH_PRINCIPAL_HEADER = "X-MS-CLIENT-PRINCIPAL"
EASY_AUTH_NAME_HEADER = "X-MS-CLIENT-PRINCIPAL-NAME"
# Easy Auth emits role claims under either type, depending on the identity provider's mapping.
ROLE_CLAIM_TYPES = frozenset({"roles", "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"})
NAME_CLAIM_TYPES = ("preferred_username", "name", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
MAX_PRINCIPAL_HEADER_LENGTH = 32 * 1024
MAX_PRINCIPAL_NAME_LENGTH = 200
UNKNOWN_PRINCIPAL_NAME = "unknown"

CSRF_COOKIE_NAME = "lookup_csrf"
# `__Host-` pins the cookie to this exact host over HTTPS, so a sibling subdomain can't plant its own value.
CSRF_SECURE_COOKIE_NAME = "__Host-lookup_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FIELD_NAME = "csrf_token"
_CSRF_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32,128}")


@dataclass(frozen=True)
class Principal:
    name: str
    roles: frozenset[str]


# Every caller's identity when auth is disabled (see Settings.validate()). Outside LOCAL the name says plainly
# that nobody signed in, because it is recorded against uploads and settings changes.
LOCAL_PRINCIPAL = Principal(name="local-dev", roles=frozenset({ROLE_ADMIN}))
UNAUTHENTICATED_PRINCIPAL = Principal(name="unauthenticated", roles=frozenset({ROLE_ADMIN}))


class SigningKey(Protocol):
    @property
    def key(self) -> Any: ...


class SigningKeyProvider(Protocol):
    """Resolves the key that signed a token; `jwt.PyJWKClient` satisfies this. Injectable for tests."""

    def get_signing_key_from_jwt(self, token: str) -> SigningKey: ...


class TokenVerifier:
    """Validates Entra v2.0 access tokens: signature (cached JWKS), issuer, audience and expiry."""

    def __init__(self, tenant_id: str, audience: str, signing_keys: SigningKeyProvider | None = None) -> None:
        self._audience = audience
        # v1 tokens (the app registration default) use the sts.windows.net issuer; both are this tenant's.
        self._issuers = [f"https://login.microsoftonline.com/{tenant_id}/v2.0", f"https://sts.windows.net/{tenant_id}/"]
        self._signing_keys: SigningKeyProvider = signing_keys or jwt.PyJWKClient(
            JWKS_URL.format(tenant=tenant_id), cache_keys=True, timeout=JWKS_TIMEOUT_SECONDS
        )

    def verify(self, token: str) -> Principal:
        try:
            signing_key = self._signing_keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuers,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise _bearer_unauthorized("Token has expired") from exc
        except jwt.PyJWKClientConnectionError as exc:
            logger.error("Could not fetch the token signing keys: %s", type(exc).__name__)
            raise BackendUnavailableError("Token signing keys are unavailable") from exc
        except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
            # Only the exception type is logged: messages can quote claim values.
            logger.warning("Rejected bearer token: %s", type(exc).__name__)
            raise _bearer_unauthorized("Invalid token") from exc
        return Principal(name=_bearer_name(claims), roles=_string_set(claims.get("roles")))


def _bearer_unauthorized(detail: str) -> UnauthorizedError:
    error = UnauthorizedError(detail)
    error.headers = {"WWW-Authenticate": "Bearer"}
    return error


def _bearer_name(claims: dict[str, Any]) -> str:
    for claim in ("preferred_username", "azp", "appid", "oid", "sub"):
        value = claims.get(claim)
        if isinstance(value, str) and value:
            return value[:MAX_PRINCIPAL_NAME_LENGTH]
    return UNKNOWN_PRINCIPAL_NAME


def _string_set(value: object) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, list):
        return frozenset(item for item in value if isinstance(item, str))
    return frozenset()


def parse_easy_auth_principal(encoded: str | None, name_header: str | None = None) -> Principal:
    """Decode the base64 JSON `X-MS-CLIENT-PRINCIPAL` header; raises UnauthorizedError if absent or malformed."""
    if not encoded:
        raise UnauthorizedError("Authentication required")
    if len(encoded) > MAX_PRINCIPAL_HEADER_LENGTH:
        raise UnauthorizedError("Invalid authentication principal")
    try:
        payload = json.loads(base64.b64decode(encoded, validate=True))
    except (ValueError, RecursionError) as exc:
        raise UnauthorizedError("Invalid authentication principal") from exc
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list):
        raise UnauthorizedError("Invalid authentication principal")

    role_types = ROLE_CLAIM_TYPES | _string_set(payload.get("role_typ"))
    roles: set[str] = set()
    claim_names: dict[str, str] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_type, value = claim.get("typ"), claim.get("val")
        if not isinstance(claim_type, str) or not isinstance(value, str):
            continue
        if claim_type in role_types:
            roles.add(value)
        else:
            claim_names.setdefault(claim_type, value)

    name = (name_header or "").strip() or next((claim_names[t] for t in NAME_CLAIM_TYPES if t in claim_names), "")
    return Principal(name=(name or UNKNOWN_PRINCIPAL_NAME)[:MAX_PRINCIPAL_NAME_LENGTH], roles=frozenset(roles))


def _require_role(principal: Principal, allowed: frozenset[str]) -> Principal:
    if principal.roles.isdisjoint(allowed):
        raise ForbiddenError("Requires one of the roles: " + ", ".join(sorted(allowed)))
    return principal


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _bearer_unauthorized("A bearer token is required")
    return token.strip()


def _has_bearer_header(request: Request) -> bool:
    return request.headers.get("Authorization", "").partition(" ")[0].lower() == "bearer"


def _auth_disabled_principal(settings: Settings) -> Principal:
    return LOCAL_PRINCIPAL if settings.is_local else UNAUTHENTICATED_PRINCIPAL


def _easy_auth_principal(request: Request, allowed: frozenset[str]) -> Principal:
    settings = _settings(request)
    if not settings.auth_enabled:
        return _auth_disabled_principal(settings)
    principal = parse_easy_auth_principal(
        request.headers.get(EASY_AUTH_PRINCIPAL_HEADER), request.headers.get(EASY_AUTH_NAME_HEADER)
    )
    return _require_role(principal, allowed)


def require_api_reader(request: Request) -> Principal:
    """Lookup API: a valid Entra bearer token carrying a reader role. Sync, because a JWKS refresh does I/O."""
    settings = _settings(request)
    if not settings.auth_enabled:
        return _auth_disabled_principal(settings)
    verifier: TokenVerifier = request.app.state.token_verifier
    return _require_role(verifier.verify(_bearer_token(request)), READER_ROLES)


async def require_reader(request: Request) -> Principal:
    """GUI and admin API, read access (Easy Auth)."""
    return _easy_auth_principal(request, READER_ROLES)


async def require_editor(request: Request) -> Principal:
    """GUI and admin API, upload and settings changes (Easy Auth)."""
    return _easy_auth_principal(request, EDITOR_ROLES)


async def require_api_editor(request: Request, principal: Annotated[Principal, Depends(require_editor)]) -> Principal:
    """Admin API writes. Session-cookie callers must also send the CSRF header; bearer callers are exempt."""
    if _settings(request).auth_enabled and not _has_bearer_header(request):
        verify_csrf(request)
    return principal


def csrf_cookie_name(settings: Settings) -> str:
    return CSRF_COOKIE_NAME if settings.is_local else CSRF_SECURE_COOKIE_NAME


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def current_csrf_token(request: Request) -> tuple[str, bool]:
    """The request's CSRF token, and whether it is new (so the caller must set the cookie)."""
    existing = request.cookies.get(csrf_cookie_name(_settings(request)))
    if existing and _CSRF_TOKEN_RE.fullmatch(existing):
        return existing, False
    return new_csrf_token(), True


def set_csrf_cookie(response: Response, request: Request, token: str) -> None:
    settings = _settings(request)
    # HttpOnly is fine because forms embed the token; no script reads the cookie.
    response.set_cookie(
        csrf_cookie_name(settings), token, httponly=True, secure=not settings.is_local, samesite="lax", path="/"
    )


def verify_csrf(request: Request, form_token: str | None = None) -> None:
    """Double-submit check: the cookie must match the `X-CSRF-Token` header, or else the form field."""
    cookie = request.cookies.get(csrf_cookie_name(_settings(request)))
    submitted = request.headers.get(CSRF_HEADER_NAME) or form_token
    if not cookie or not submitted or not hmac.compare_digest(cookie.encode(), submitted.encode()):
        raise CsrfError("CSRF token missing or invalid; reload the page and try again")
