from __future__ import annotations

import base64
import dataclasses
import json
import time
import unittest
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from lookup_service.app import create_app
from lookup_service.config import AUTH_DISABLED_ACK_VALUE, Settings
from lookup_service.errors import UnauthorizedError
from lookup_service.security import (
    CSRF_HEADER_NAME,
    EASY_AUTH_NAME_HEADER,
    EASY_AUTH_PRINCIPAL_HEADER,
    MAX_PRINCIPAL_HEADER_LENGTH,
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_READER,
    parse_easy_auth_principal,
)
from tests.helpers import TEST_AUDIENCE, TEST_TENANT_ID, MemoryTableStore, csrf_headers, make_settings

SECURE_CSRF_COOKIE = "__Host-lookup_csrf"
ROLE_URI = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
V2_ISSUER = f"https://login.microsoftonline.com/{TEST_TENANT_ID}/v2.0"
V1_ISSUER = f"https://sts.windows.net/{TEST_TENANT_ID}/"
LOOKUP_URL = "/api/v1/lookup/health_board_mapping?k=224"
HEALTH_BOARD_CSV = b"msh3,health_board\n224,VCC-NEW\n"

_SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass(frozen=True)
class FakeSigningKey:
    key: Any


class FakeSigningKeys:
    """Stands in for the JWKS client: no network, always returns the test public key (or raises `error`)."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return FakeSigningKey(_SIGNING_KEY.public_key())


def make_token(
    roles: tuple[str, ...] = (ROLE_READER,),
    audience: str = TEST_AUDIENCE,
    issuer: str = V2_ISSUER,
    expires_in: int = 3600,
    key: Any = _SIGNING_KEY,
    **claims: Any,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {"aud": audience, "iss": issuer, "iat": now, "nbf": now - 5, "exp": now + expires_in,
                               "roles": list(roles), "azp": "transformer-app", **claims}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "test-key"})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def encode_principal(payload: Any) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def easy_auth_headers(*roles: str, name: str | None = "alice@nhs.wales", role_type: str = "roles") -> dict[str, str]:
    claims = [{"typ": role_type, "val": role} for role in roles]
    headers = {EASY_AUTH_PRINCIPAL_HEADER: encode_principal({"auth_typ": "aad", "claims": claims})}
    if name:
        headers[EASY_AUTH_NAME_HEADER] = name
    return headers


def auth_client(store: MemoryTableStore | None = None, signing_keys: FakeSigningKeys | None = None) -> TestClient:
    """A client for a non-LOCAL app (auth enforced, Secure cookies), so it talks HTTPS."""
    app = create_app(make_settings(environment="DEV"), store, signing_keys or FakeSigningKeys())
    return TestClient(app, base_url="https://testserver")


class BearerTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = FakeSigningKeys()
        self.client = self.enterContext(auth_client(signing_keys=self.keys))

    def get_lookup(self, token: str | None = None, **headers: str) -> Any:
        return self.client.get(LOOKUP_URL, headers=bearer(token) if token else headers)

    def assert_unauthorized(self, response: Any) -> None:
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(response.json()["error"], "unauthorized")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_missing_token(self) -> None:
        self.assert_unauthorized(self.get_lookup())

    def test_other_scheme_or_empty_token(self) -> None:
        for header in ("Basic dXNlcjpwYXNz", "Bearer", "Bearer   ", "token-without-scheme"):
            with self.subTest(header=header):
                self.assert_unauthorized(self.get_lookup(Authorization=header))

    def test_malformed_token(self) -> None:
        for token in ("not-a-jwt", "a.b.c", "x" * 500):
            with self.subTest(token=token[:10]):
                self.assert_unauthorized(self.get_lookup(token))

    def test_expired_token(self) -> None:
        response = self.get_lookup(make_token(expires_in=-3600))
        self.assert_unauthorized(response)
        self.assertEqual(response.json()["detail"], "Token has expired")

    def test_wrong_audience(self) -> None:
        self.assert_unauthorized(self.get_lookup(make_token(audience="api://someone-else")))

    def test_wrong_issuer(self) -> None:
        wrong_tenant = "https://login.microsoftonline.com/99999999-0000-0000-0000-000000000000/v2.0"
        for issuer in (wrong_tenant, "https://evil.example/", V2_ISSUER + "x"):
            with self.subTest(issuer=issuer):
                self.assert_unauthorized(self.get_lookup(make_token(issuer=issuer)))

    def test_wrong_signature(self) -> None:
        self.assert_unauthorized(self.get_lookup(make_token(key=_OTHER_KEY)))

    def test_unsigned_token(self) -> None:
        payload = {"aud": TEST_AUDIENCE, "iss": V2_ISSUER, "exp": int(time.time()) + 3600, "roles": [ROLE_ADMIN]}
        self.assert_unauthorized(self.get_lookup(jwt.encode(payload, "", algorithm="none")))

    def test_token_without_expiry(self) -> None:
        payload = {"aud": TEST_AUDIENCE, "iss": V2_ISSUER, "roles": [ROLE_READER]}
        self.assert_unauthorized(self.get_lookup(jwt.encode(payload, _SIGNING_KEY, algorithm="RS256")))

    def test_unknown_signing_key(self) -> None:
        self.keys.error = jwt.PyJWKClientError("Unable to find a signing key that matches")
        self.assert_unauthorized(self.get_lookup(make_token()))

    def test_unreachable_jwks_endpoint_is_503_not_401(self) -> None:
        self.keys.error = jwt.PyJWKClientConnectionError("connection refused")
        response = self.get_lookup(make_token())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "backend_unavailable")

    def test_each_reader_role_is_accepted(self) -> None:
        for role in (ROLE_READER, ROLE_EDITOR, ROLE_ADMIN):
            with self.subTest(role=role):
                response = self.get_lookup(make_token(roles=(role,)))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["value"], "VCC")

    def test_token_without_a_lookup_role_is_forbidden(self) -> None:
        for roles in ((), ("Some.Other.Role",)):
            with self.subTest(roles=roles):
                response = self.get_lookup(make_token(roles=roles))
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"], "forbidden")

    def test_token_without_roles_claim_is_forbidden(self) -> None:
        payload = {"aud": TEST_AUDIENCE, "iss": V2_ISSUER, "exp": int(time.time()) + 3600}
        response = self.get_lookup(jwt.encode(payload, _SIGNING_KEY, algorithm="RS256"))
        self.assertEqual(response.status_code, 403)

    def test_v1_issuer_of_the_same_tenant_is_accepted(self) -> None:
        self.assertEqual(self.get_lookup(make_token(issuer=V1_ISSUER)).status_code, 200)

    def test_token_is_never_logged_or_echoed(self) -> None:
        token = make_token(audience="api://someone-else")
        with self.assertLogs("lookup_service.security", level="WARNING") as logs:
            response = self.get_lookup(token)
        self.assertNotIn(token, "\n".join(logs.output))
        self.assertNotIn(token, response.text)

    def test_lookup_ignores_easy_auth_headers(self) -> None:
        self.assert_unauthorized(self.get_lookup(**easy_auth_headers(ROLE_ADMIN)))

    def test_not_ready_is_still_reported_with_a_valid_token(self) -> None:
        # Without entering the context manager the lifespan doesn't run, so no tables are loaded.
        client = auth_client(signing_keys=self.keys)
        response = client.get(LOOKUP_URL, headers=bearer(make_token()))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "not_ready")


class EasyAuthPrincipalTests(unittest.TestCase):
    def test_parses_name_and_roles(self) -> None:
        headers = easy_auth_headers(ROLE_EDITOR, ROLE_READER)
        principal = parse_easy_auth_principal(headers[EASY_AUTH_PRINCIPAL_HEADER], headers[EASY_AUTH_NAME_HEADER])
        self.assertEqual(principal.name, "alice@nhs.wales")
        self.assertEqual(principal.roles, {ROLE_EDITOR, ROLE_READER})

    def test_role_claim_uri_and_declared_role_type(self) -> None:
        for role_type in (ROLE_URI, "custom-role-type"):
            with self.subTest(role_type=role_type):
                payload = {"role_typ": "custom-role-type", "claims": [{"typ": role_type, "val": ROLE_ADMIN}]}
                self.assertEqual(parse_easy_auth_principal(encode_principal(payload)).roles, {ROLE_ADMIN})

    def test_other_claims_are_not_roles(self) -> None:
        payload = {"claims": [{"typ": "groups", "val": ROLE_ADMIN}, {"typ": "preferred_username", "val": "bob"}]}
        principal = parse_easy_auth_principal(encode_principal(payload))
        self.assertEqual((principal.name, principal.roles), ("bob", frozenset()))

    def test_name_falls_back_to_unknown(self) -> None:
        self.assertEqual(parse_easy_auth_principal(encode_principal({"claims": []})).name, "unknown")

    def test_malformed_claims_are_skipped(self) -> None:
        payload = {"claims": ["x", {"typ": "roles"}, {"typ": 1, "val": "y"}, {"typ": "roles", "val": ROLE_READER}]}
        self.assertEqual(parse_easy_auth_principal(encode_principal(payload)).roles, {ROLE_READER})

    def test_missing_or_garbage_header_is_unauthorized(self) -> None:
        garbage = (
            None, "", "!!!not-base64!!!", base64.b64encode(b"not json").decode(),
            base64.b64encode(b"\xff\xfe").decode(), encode_principal([1, 2]), encode_principal("text"),
            encode_principal({"claims": "roles"}), encode_principal({}), "A" * (MAX_PRINCIPAL_HEADER_LENGTH + 1),
            base64.b64encode(b"[" * 100_000).decode()[:MAX_PRINCIPAL_HEADER_LENGTH],
        )
        for value in garbage:
            with self.subTest(value=(value or "")[:20]):
                with self.assertRaises(UnauthorizedError):
                    parse_easy_auth_principal(value)


class GuiRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryTableStore()
        self.client = self.enterContext(auth_client(self.store))
        self.reader = easy_auth_headers(ROLE_READER, name="reader@nhs.wales")
        self.editor = easy_auth_headers(ROLE_EDITOR, name="editor@nhs.wales")
        self.admin = easy_auth_headers(ROLE_ADMIN, name="admin@nhs.wales", role_type=ROLE_URI)

    def csrf(self, auth: dict[str, str]) -> dict[str, str]:
        return {**auth, **csrf_headers(self.client, SECURE_CSRF_COOKIE, auth)}

    def upload_form(self, headers: dict[str, str]) -> Any:
        return self.client.post("/upload", data={"table": "health_board_mapping"}, headers=headers,
                                files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")}, follow_redirects=False)

    def test_missing_or_garbage_principal_is_unauthorized(self) -> None:
        for headers in ({}, {EASY_AUTH_PRINCIPAL_HEADER: "garbage"}, {EASY_AUTH_NAME_HEADER: "alice@nhs.wales"}):
            for path in ("/", "/upload", "/tables/ward_map", "/api/v1/tables", "/api/v1/tables/ward_map"):
                with self.subTest(path=path, headers=list(headers)):
                    response = self.client.get(path, headers=headers)
                    self.assertEqual((response.status_code, response.json()["error"]), (401, "unauthorized"))

    def test_principal_without_a_lookup_role_is_forbidden(self) -> None:
        response = self.client.get("/", headers=easy_auth_headers("Some.Other.Role"))
        self.assertEqual((response.status_code, response.json()["error"]), (403, "forbidden"))

    def test_every_role_can_read(self) -> None:
        for headers in (self.reader, self.editor, self.admin):
            for path in ("/", "/tables/ward_map", "/upload", "/api/v1/tables", "/api/v1/tables/ward_map/rows"):
                with self.subTest(path=path, headers=headers[EASY_AUTH_NAME_HEADER]):
                    self.assertEqual(self.client.get(path, headers=headers).status_code, 200)

    def test_bearer_token_alone_does_not_open_the_gui(self) -> None:
        response = self.client.get("/api/v1/tables", headers=bearer(make_token(roles=(ROLE_ADMIN,))))
        self.assertEqual(response.status_code, 401)

    def test_reader_sees_no_edit_controls(self) -> None:
        page = self.client.get("/tables/ward_map", headers=self.reader).text
        self.assertNotIn("Cache settings", page)
        self.assertNotIn("Replace data", page)
        self.assertIn(ROLE_EDITOR, self.client.get("/upload", headers=self.reader).text)
        self.assertIn("Cache settings", self.client.get("/tables/ward_map", headers=self.editor).text)

    def test_reader_cannot_upload_or_change_settings_in_the_gui(self) -> None:
        headers = self.csrf(self.reader)
        self.assertEqual(self.upload_form(headers).status_code, 403)
        response = self.client.post("/tables/ward_map/settings", data={"preload": "on"}, headers=headers)
        self.assertEqual((response.status_code, response.json()["error"]), (403, "forbidden"))
        self.assertEqual(self.store.rows["health_board_mapping"][("224",)].values["health_board"], "VCC")
        self.assertFalse(self.store.records["ward_map"].definition.preload)

    def test_reader_cannot_upload_or_patch_through_the_api(self) -> None:
        headers = self.csrf(self.reader)
        upload = self.client.post("/api/v1/tables/health_board_mapping/uploads", headers=headers,
                                  files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")})
        patch = self.client.patch("/api/v1/tables/ward_map", json={"preload": True}, headers=headers)
        for response in (upload, patch):
            self.assertEqual((response.status_code, response.json()["error"]), (403, "forbidden"))
        self.assertFalse(self.store.records["ward_map"].definition.preload)

    def test_editor_and_admin_can_upload_and_the_actor_is_their_name(self) -> None:
        for auth, name in ((self.editor, "editor@nhs.wales"), (self.admin, "admin@nhs.wales")):
            with self.subTest(name=name):
                response = self.upload_form(self.csrf(auth))
                self.assertEqual(response.status_code, 303, response.text)
                self.assertEqual(self.store.records["health_board_mapping"].stats.last_upload_by, name)

    def test_editor_can_change_settings_in_the_gui(self) -> None:
        response = self.client.post("/tables/ward_map/settings", data={"preload": "on"},
                                    headers=self.csrf(self.editor), follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(self.store.records["ward_map"].definition.preload)

    def test_editor_can_upload_and_patch_through_the_api(self) -> None:
        headers = self.csrf(self.editor)
        upload = self.client.post("/api/v1/tables/health_board_mapping/uploads", headers=headers,
                                  files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")})
        self.assertEqual(upload.status_code, 201, upload.text)
        self.assertEqual(self.store.records["health_board_mapping"].stats.last_upload_by, "editor@nhs.wales")
        patch = self.client.patch("/api/v1/tables/ward_map", json={"preload": True}, headers=headers)
        self.assertEqual(patch.status_code, 200, patch.text)


class CsrfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryTableStore()
        self.client = self.enterContext(auth_client(self.store))
        self.editor = easy_auth_headers(ROLE_EDITOR)

    def post_settings(self, headers: dict[str, str], **data: str) -> Any:
        return self.client.post("/tables/ward_map/settings", data={"preload": "on", **data},
                                headers={**self.editor, **headers}, follow_redirects=False)

    def assert_rejected(self, response: Any) -> None:
        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("csrf_failed", response.text)
        self.assertFalse(self.store.records["ward_map"].definition.preload)

    def test_cookie_is_issued_with_secure_attributes(self) -> None:
        response = self.client.get("/", headers=self.editor)
        cookie = response.headers["set-cookie"]
        self.assertTrue(cookie.startswith(SECURE_CSRF_COOKIE + "="), cookie)
        for attribute in ("Secure", "HttpOnly", "SameSite=lax", "Path=/"):
            self.assertIn(attribute, cookie)
        self.assertNotIn("Domain", cookie)

    def test_local_cookie_is_not_secure_and_is_not_host_prefixed(self) -> None:
        with TestClient(create_app(make_settings())) as client:
            cookie = client.get("/").headers["set-cookie"]
        self.assertTrue(cookie.startswith("lookup_csrf="), cookie)
        self.assertNotIn("Secure", cookie)

    def test_existing_cookie_is_reused_and_embedded_in_forms(self) -> None:
        self.client.get("/tables/ward_map", headers=self.editor)
        token = self.client.cookies.get(SECURE_CSRF_COOKIE)
        second = self.client.get("/tables/ward_map", headers=self.editor)
        self.assertNotIn("set-cookie", second.headers)
        self.assertIn(f'name="csrf_token" value="{token}"', second.text)

    def test_malformed_cookie_is_replaced(self) -> None:
        self.client.cookies.set(SECURE_CSRF_COOKIE, "short")
        response = self.client.get("/", headers=self.editor)
        self.assertIn(SECURE_CSRF_COOKIE + "=", response.headers["set-cookie"])
        self.assertNotIn("=short;", response.headers["set-cookie"])

    def test_missing_token_is_rejected(self) -> None:
        self.client.get("/", headers=self.editor)
        self.assert_rejected(self.post_settings({}))

    def test_missing_cookie_is_rejected(self) -> None:
        self.assert_rejected(self.post_settings({CSRF_HEADER_NAME: "A" * 43}, csrf_token="A" * 43))

    def test_mismatched_token_is_rejected(self) -> None:
        self.client.get("/", headers=self.editor)
        self.assert_rejected(self.post_settings({CSRF_HEADER_NAME: "B" * 43}))
        self.assert_rejected(self.post_settings({}, csrf_token="B" * 43))

    def test_non_ascii_token_is_rejected_not_an_error(self) -> None:
        self.client.get("/", headers=self.editor)
        self.assert_rejected(self.post_settings({}, csrf_token="é" * 43))

    def test_matching_header_or_form_field_is_accepted(self) -> None:
        token = csrf_headers(self.client, SECURE_CSRF_COOKIE, self.editor)[CSRF_HEADER_NAME]
        self.assertEqual(self.post_settings({CSRF_HEADER_NAME: token}).status_code, 303)
        self.assertEqual(self.post_settings({}, csrf_token=token, preload="").status_code, 303)

    def test_upload_form_requires_the_token(self) -> None:
        self.client.get("/", headers=self.editor)
        response = self.client.post("/upload", data={"table": "health_board_mapping"}, headers=self.editor,
                                    files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.store.rows["health_board_mapping"][("224",)].values["health_board"], "VCC")

    def test_api_writes_with_a_session_need_the_token(self) -> None:
        self.client.get("/", headers=self.editor)
        upload = self.client.post("/api/v1/tables/health_board_mapping/uploads", headers=self.editor,
                                  files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")})
        patch = self.client.patch("/api/v1/tables/ward_map", json={"preload": True}, headers=self.editor)
        for response in (upload, patch):
            self.assertEqual((response.status_code, response.json()["error"]), (403, "csrf_failed"))
        self.assertEqual(self.store.rows["health_board_mapping"][("224",)].values["health_board"], "VCC")

    def test_api_writes_with_a_bearer_header_are_exempt(self) -> None:
        headers = {**self.editor, **bearer("opaque-to-easy-auth-validated")}
        response = self.client.patch("/api/v1/tables/ward_map", json={"preload": True}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)

    def test_bearer_exemption_still_needs_an_authenticated_principal(self) -> None:
        response = self.client.patch("/api/v1/tables/ward_map", json={"preload": True},
                                     headers=bearer(make_token(roles=(ROLE_ADMIN,))))
        self.assertEqual(response.status_code, 401)

    def test_get_requests_need_no_token(self) -> None:
        self.assertEqual(self.client.get("/tables/ward_map", headers=self.editor).status_code, 200)


class StartupGuardTests(unittest.TestCase):
    def test_non_local_without_auth_configuration_refuses_to_start(self) -> None:
        for field in ("auth_tenant_id", "auth_audience"):
            with self.subTest(missing=field):
                overrides: dict[str, Any] = {field: None}
                settings = dataclasses.replace(make_settings(environment="DEV"), **overrides)
                with self.assertRaisesRegex(RuntimeError, "Authentication is not configured"):
                    create_app(settings)

    def test_auth_cannot_be_disabled_outside_local_dev_and_tst(self) -> None:
        settings = dataclasses.replace(make_settings(environment="PRD"), auth_disabled=True,
                                       auth_disabled_ack=AUTH_DISABLED_ACK_VALUE)
        with self.assertRaisesRegex(RuntimeError, "only allowed when ENVIRONMENT is one of"):
            create_app(settings)

    def test_dev_and_tst_refuse_to_disable_auth_without_the_acknowledgement(self) -> None:
        for environment in ("DEV", "TST"):
            with self.subTest(environment=environment):
                settings = dataclasses.replace(make_settings(environment=environment), auth_disabled=True)
                with self.assertRaisesRegex(RuntimeError, "also needs LOOKUP_AUTH_DISABLED_ACK="):
                    create_app(settings)

    def test_local_must_explicitly_disable_auth_or_configure_it(self) -> None:
        settings = dataclasses.replace(make_settings(), auth_disabled=False)
        with self.assertRaisesRegex(RuntimeError, "LOOKUP_AUTH_DISABLED=true"):
            create_app(settings)

    def test_local_can_enforce_auth_when_configured(self) -> None:
        settings = dataclasses.replace(make_settings(), auth_disabled=False, auth_tenant_id=TEST_TENANT_ID,
                                       auth_audience=TEST_AUDIENCE)
        with TestClient(create_app(settings, signing_keys=FakeSigningKeys())) as client:
            self.assertEqual(client.get(LOOKUP_URL).status_code, 401)
            self.assertEqual(client.get("/").status_code, 401)


class LocalAuthDisabledTests(unittest.TestCase):
    def test_everything_is_open_with_a_local_admin_principal(self) -> None:
        store = MemoryTableStore()
        with TestClient(create_app(make_settings(), store)) as client:
            self.assertEqual(client.get(LOOKUP_URL).status_code, 200)
            self.assertEqual(client.get("/").status_code, 200)
            # Header-supplied principals are ignored when auth is disabled.
            response = client.patch("/api/v1/tables/ward_map", json={"preload": True},
                                    headers=easy_auth_headers("Some.Other.Role"))
            self.assertEqual(response.status_code, 200, response.text)
            upload = client.post("/api/v1/tables/health_board_mapping/uploads",
                                 files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")})
        self.assertEqual(upload.status_code, 201, upload.text)
        self.assertEqual(store.records["health_board_mapping"].stats.last_upload_by, "local-dev")

    def test_no_unauthenticated_banner_locally(self) -> None:
        with TestClient(create_app(make_settings(), MemoryTableStore())) as client:
            self.assertNotIn("auth-disabled-banner", client.get("/").text)


class UnauthenticatedTrialTests(unittest.TestCase):
    """DEV/TST with LOOKUP_AUTH_DISABLED plus the acknowledgement (plan Phase 1.25)."""

    def _settings(self, environment: str = "DEV") -> Settings:
        return dataclasses.replace(make_settings(environment=environment), auth_disabled=True,
                                   auth_disabled_ack=AUTH_DISABLED_ACK_VALUE)

    def test_everything_is_open_and_recorded_as_unauthenticated(self) -> None:
        store = MemoryTableStore()
        with TestClient(create_app(self._settings(), store)) as client:
            self.assertEqual(client.get(LOOKUP_URL).status_code, 200)
            # Header-supplied principals are ignored when auth is disabled.
            response = client.patch("/api/v1/tables/ward_map", json={"preload": True},
                                    headers=easy_auth_headers("Some.Other.Role"))
            self.assertEqual(response.status_code, 200, response.text)
            upload = client.post("/api/v1/tables/health_board_mapping/uploads",
                                 files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")})
        self.assertEqual(upload.status_code, 201, upload.text)
        self.assertEqual(store.records["health_board_mapping"].stats.last_upload_by, "unauthenticated")

    def test_every_gui_page_shows_the_warning_banner(self) -> None:
        with TestClient(create_app(self._settings("TST"), MemoryTableStore())) as client:
            for path in ("/", "/tables/ward_map", "/upload", "/tables/no_such_table"):
                with self.subTest(path=path):
                    page = client.get(path).text
                    self.assertIn("auth-disabled-banner", page)
                    self.assertIn("Authentication is disabled in TST", page)

    def test_startup_logs_a_warning(self) -> None:
        with self.assertLogs("lookup_service.app", level="WARNING") as logs:
            create_app(self._settings())
        self.assertIn("AUTHENTICATION IS DISABLED in DEV", logs.output[0])


class UnauthenticatedEndpointTests(unittest.TestCase):
    def test_health_and_static_assets_stay_open(self) -> None:
        with auth_client() as client:
            self.assertEqual(client.get("/health/live").json(), {"status": "ok"})
            self.assertEqual(client.get("/health/ready").status_code, 200)
            self.assertEqual(client.get("/static/css/lookup.css").status_code, 200)

    def test_not_ready_is_reported_without_credentials(self) -> None:
        client = auth_client()
        self.assertEqual(client.get("/health/live").status_code, 200)
        self.assertEqual(client.get("/health/ready").status_code, 503)


if __name__ == "__main__":
    unittest.main()
