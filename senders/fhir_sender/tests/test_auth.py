import unittest
from typing import Any
from unittest.mock import MagicMock

import requests

from fhir_sender.auth import ApiKeyAuth, OAuth2ClientCredentialsAuth
from fhir_sender.errors import AuthorizationDeliveryError, TransientDeliveryError


def _token_response(status: int = 200, body: Any = None) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.json.return_value = body if body is not None else {"access_token": "tok", "expires_in": 3600}
    return response


class ApiKeyAuthTests(unittest.TestCase):
    def test_sends_x_api_key_header(self) -> None:
        auth = ApiKeyAuth("abc")
        self.assertEqual(auth.headers(), {"X-API-Key": "abc"})
        self.assertFalse(auth.invalidate())

    def test_blank_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ApiKeyAuth("  ")


class OAuth2AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = MagicMock(spec=requests.Session)
        self.now = 0.0
        self.auth = OAuth2ClientCredentialsAuth(
            "https://auth.example.test/oauth2/token", "id", "secret", "target-entity:1",
            session=self.session, monotonic=lambda: self.now,
        )

    def test_plain_http_token_endpoint_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OAuth2ClientCredentialsAuth("http://auth.example.test/token", "id", "secret", "scope")

    def test_requests_token_with_client_credentials_form(self) -> None:
        self.session.post.return_value = _token_response()

        self.assertEqual(self.auth.headers(), {"Authorization": "Bearer tok"})

        data = self.session.post.call_args.kwargs["data"]
        self.assertEqual(data["grant_type"], "client_credentials")
        self.assertEqual(data["scope"], "target-entity:1")

    def test_token_is_cached_until_near_expiry(self) -> None:
        self.session.post.return_value = _token_response()
        self.auth.headers()
        self.now = 3000
        self.auth.headers()
        self.assertEqual(self.session.post.call_count, 1)

        self.now = 3541  # inside the 60s refresh margin of the 3600s lifetime
        self.auth.headers()
        self.assertEqual(self.session.post.call_count, 2)

    def test_invalidate_forces_new_token(self) -> None:
        self.session.post.return_value = _token_response()
        self.auth.headers()
        self.assertTrue(self.auth.invalidate())
        self.auth.headers()
        self.assertEqual(self.session.post.call_count, 2)

    def test_rejected_credentials_raise_authorization_error(self) -> None:
        self.session.post.return_value = _token_response(401)
        with self.assertRaises(AuthorizationDeliveryError):
            self.auth.headers()

    def test_server_error_and_network_failure_are_transient(self) -> None:
        self.session.post.return_value = _token_response(503)
        with self.assertRaises(TransientDeliveryError):
            self.auth.headers()

        self.session.post.side_effect = requests.exceptions.ConnectionError("down")
        with self.assertRaises(TransientDeliveryError):
            self.auth.headers()

    def test_response_without_access_token_is_transient(self) -> None:
        self.session.post.return_value = _token_response(200, {"unexpected": True})
        with self.assertRaises(TransientDeliveryError):
            self.auth.headers()


if __name__ == "__main__":
    unittest.main()
