import unittest
from typing import Any, Optional
from unittest.mock import MagicMock

import requests

from fhir_sender.auth import ApiKeyAuth
from fhir_sender.errors import (
    AuthorizationDeliveryError,
    PermanentDeliveryError,
    TransientDeliveryError,
)
from fhir_sender.fhir_sender_client import FhirSenderClient

ENDPOINT = "https://wpas-fhir.example.test/fhir/r4/$process-message"
STATUS = "https://wpas-fhir.example.test/fhir/r4/status/12345"
BUNDLE = '{"resourceType":"Bundle","type":"message"}'


def _response(status: int, headers: Optional[dict[str, str]] = None, body: Optional[Any] = None) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.headers = headers or {}
    response.reason = "reason"
    response.text = "" if body is None else str(body)
    if body is None:
        response.json.side_effect = ValueError("no body")
    else:
        response.json.return_value = body
    return response


def _outcome(severity: str, text: str = "detail") -> dict[str, Any]:
    issue = {"severity": severity, "code": "x", "details": {"text": text}}
    return {"resourceType": "OperationOutcome", "issue": [issue]}


class FhirSenderClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = MagicMock(spec=requests.Session)
        self.sleeps: list[float] = []
        self.clock = 0.0

    def _monotonic(self) -> float:
        return self.clock

    def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock += seconds

    def _client(self, **kwargs: Any) -> FhirSenderClient:
        return FhirSenderClient(
            ENDPOINT, ApiKeyAuth("key"), session=self.session,
            sleep=self._sleep, monotonic=self._monotonic, **kwargs,
        )

    def test_accepted_then_polled_to_success(self) -> None:
        self.session.request.side_effect = [
            _response(202, {"Content-Location": STATUS}),
            _response(202, {"Retry-After": "10", "X-Progress": "Processing"}),
            _response(200, body=_outcome("information")),
        ]

        self._client().send_bundle(BUNDLE)

        post_call = self.session.request.call_args_list[0]
        self.assertEqual(post_call.args, ("POST", ENDPOINT))
        self.assertEqual(post_call.kwargs["headers"]["Content-Type"], "application/fhir+json")
        self.assertEqual(post_call.kwargs["headers"]["Accept"], "application/fhir+json")
        self.assertEqual(post_call.kwargs["headers"]["X-API-Key"], "key")
        self.assertEqual(post_call.kwargs["data"], BUNDLE.encode())
        self.assertEqual(self.session.request.call_args_list[1].args, ("GET", STATUS))
        self.assertEqual(self.sleeps, [10.0])

    def test_relative_content_location_is_resolved(self) -> None:
        self.session.request.side_effect = [
            _response(202, {"Content-Location": "/fhir/r4/status/12345"}),
            _response(200, body=_outcome("information")),
        ]
        self._client().send_bundle(BUNDLE)
        self.assertEqual(self.session.request.call_args_list[1].args, ("GET", STATUS))

    def test_status_url_on_other_host_is_rejected(self) -> None:
        self.session.request.side_effect = [_response(202, {"Content-Location": "https://evil.test/status/1"})]
        with self.assertRaises(PermanentDeliveryError):
            self._client().send_bundle(BUNDLE)
        self.assertEqual(self.session.request.call_count, 1)

    def test_missing_content_location_is_transient(self) -> None:
        self.session.request.side_effect = [_response(202)]
        with self.assertRaises(TransientDeliveryError):
            self._client().send_bundle(BUNDLE)

    def test_error_outcome_on_200_is_permanent(self) -> None:
        self.session.request.side_effect = [
            _response(202, {"Content-Location": STATUS}),
            _response(200, body=_outcome("error", "Invalid message format")),
        ]
        with self.assertRaises(PermanentDeliveryError) as ctx:
            self._client().send_bundle(BUNDLE)
        self.assertIn("Invalid message format", ctx.exception.detail)

    def test_polling_gives_up_after_timeout(self) -> None:
        self.session.request.side_effect = [_response(202, {"Content-Location": STATUS})] + [
            _response(202, {"Retry-After": "30"}) for _ in range(10)
        ]
        with self.assertRaises(TransientDeliveryError):
            self._client(poll_timeout_seconds=60).send_bundle(BUNDLE)

    def test_400_409_and_404_are_not_retried(self) -> None:
        for status in (400, 404, 409):
            with self.subTest(status=status):
                self.session.request.reset_mock()
                self.session.request.side_effect = [_response(status, body=_outcome("error", "nope"))]
                with self.assertRaises(PermanentDeliveryError) as ctx:
                    self._client().send_bundle(BUNDLE)
                self.assertEqual(ctx.exception.status_code, status)
                self.assertEqual(self.session.request.call_count, 1)

    def test_401_and_403_are_not_retried_with_api_key(self) -> None:
        for status in (401, 403):
            with self.subTest(status=status):
                self.session.request.reset_mock()
                self.session.request.side_effect = [_response(status)]
                with self.assertRaises(AuthorizationDeliveryError):
                    self._client().send_bundle(BUNDLE)
                self.assertEqual(self.session.request.call_count, 1)

    def test_401_with_oauth_refreshes_token_once(self) -> None:
        auth = MagicMock()
        auth.headers.return_value = {"Authorization": "Bearer t"}
        auth.invalidate.return_value = True
        self.session.request.side_effect = [_response(401), _response(401)]
        client = FhirSenderClient(ENDPOINT, auth, session=self.session, sleep=self._sleep)

        with self.assertRaises(AuthorizationDeliveryError):
            client.send_bundle(BUNDLE)

        self.assertEqual(self.session.request.call_count, 2)
        auth.invalidate.assert_called_once()

    def test_429_waits_for_retry_after_then_succeeds(self) -> None:
        self.session.request.side_effect = [
            _response(429, {"Retry-After": "7"}),
            _response(202, {"Content-Location": STATUS}),
            _response(200, body=_outcome("information")),
        ]
        self._client().send_bundle(BUNDLE)
        self.assertEqual(self.sleeps, [7.0])

    def test_retry_after_is_capped(self) -> None:
        self.session.request.side_effect = [
            _response(429, {"Retry-After": "9999"}),
            _response(200, body=_outcome("information")),
        ]
        self._client(max_retry_after_seconds=60).send_bundle(BUNDLE)
        self.assertEqual(self.sleeps, [60.0])

    def test_500_retries_with_exponential_backoff_then_fails(self) -> None:
        self.session.request.side_effect = [_response(500, body=_outcome("error", "boom"))] * 3
        with self.assertRaises(TransientDeliveryError):
            self._client(max_attempts=3, backoff_seconds=2).send_bundle(BUNDLE)
        self.assertEqual(self.session.request.call_count, 3)
        self.assertEqual(self.sleeps, [2.0, 4.0])

    def test_network_error_is_retried_then_succeeds(self) -> None:
        self.session.request.side_effect = [
            requests.exceptions.ConnectionError("down"),
            requests.exceptions.Timeout("slow"),
            _response(200, body=_outcome("information")),
        ]
        self._client(max_attempts=3).send_bundle(BUNDLE)
        self.assertEqual(self.session.request.call_count, 3)

    def test_redirects_are_not_followed(self) -> None:
        self.session.request.side_effect = [_response(302, {"Location": "https://other.test"})]
        with self.assertRaises(PermanentDeliveryError):
            self._client().send_bundle(BUNDLE)
        self.assertFalse(self.session.request.call_args.kwargs["allow_redirects"])

    def test_plain_http_requires_explicit_opt_in(self) -> None:
        with self.assertRaises(ValueError):
            FhirSenderClient("http://localhost/$process-message", ApiKeyAuth("key"))
        FhirSenderClient("http://localhost/$process-message", ApiKeyAuth("key"), allow_insecure_http=True)


if __name__ == "__main__":
    unittest.main()
