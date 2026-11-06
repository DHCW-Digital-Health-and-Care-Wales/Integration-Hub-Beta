"""Tests for the Promptly $process-message mock (scenario selection via Bundle.id)."""
from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from http_mock_receiver.application import app
from http_mock_receiver.fhir_handler import TERMINAL_RETENTION_SECONDS, FhirMockState

_client = TestClient(app, raise_server_exceptions=False)
_URL = "/fhir/r4/$process-message"


def _bundle(bundle_id: str = "") -> str:
    bundle: dict[str, object] = {"resourceType": "Bundle", "type": "message", "entry": []}
    if bundle_id:
        bundle["id"] = bundle_id
    return json.dumps(bundle)


def _job_id(content_location: str) -> str:
    return content_location.rsplit("/", 1)[-1]


class FhirMockStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = FhirMockState()

    def test_default_flow_accepts_polls_twice_then_succeeds(self) -> None:
        accepted = self.state.submit(_bundle(), "http://host/")
        self.assertEqual(accepted.status_code, 202)
        job_id = _job_id(accepted.headers["Content-Location"])

        self.assertEqual(self.state.status(job_id).status_code, 202)
        self.assertEqual(self.state.status(job_id).status_code, 202)
        final = self.state.status(job_id)
        self.assertEqual(final.status_code, 200)
        assert final.body is not None
        self.assertEqual(final.body["issue"][0]["severity"], "information")

    def test_immediate_failure_scenarios(self) -> None:
        for status in (400, 401, 403, 404, 409, 429, 500):
            with self.subTest(status=status):
                result = self.state.submit(_bundle(f"mock-{status}"), "http://host/")
                self.assertEqual(result.status_code, status)
                self.assertEqual("Retry-After" in result.headers, status == 429)

    def test_fail_once_scenario_recovers_on_retry(self) -> None:
        self.assertEqual(self.state.submit(_bundle("mock-500-once"), "http://host/").status_code, 500)
        self.assertEqual(self.state.submit(_bundle("mock-500-once"), "http://host/").status_code, 202)

    def test_error_outcome_scenario_completes_with_error_severity(self) -> None:
        job_id = _job_id(self.state.submit(_bundle("mock-error-outcome"), "http://host/").headers["Content-Location"])
        result = self.state.status(job_id)
        while result.status_code == 202:
            result = self.state.status(job_id)
        assert result.body is not None
        self.assertEqual(result.body["issue"][0]["severity"], "error")

    def test_invalid_bodies_are_rejected_with_400(self) -> None:
        for body in ("not json", "[]", '{"resourceType":"Patient"}', '{"resourceType":"Bundle","type":"batch"}'):
            with self.subTest(body=body):
                self.assertEqual(self.state.submit(body, "http://host/").status_code, 400)

    def test_unknown_status_id_is_404(self) -> None:
        self.assertEqual(self.state.status("nope").status_code, 404)

    def test_terminal_status_is_repeatable_then_expires(self) -> None:
        now = [0.0]
        state = FhirMockState(clock=lambda: now[0])
        job_id = _job_id(state.submit(_bundle(), "http://host/").headers["Content-Location"])
        result = state.status(job_id)
        while result.status_code == 202:
            result = state.status(job_id)

        # A retried GET (e.g. after a dropped connection) must see the same outcome, not a 404
        self.assertEqual(state.status(job_id).body, result.body)

        now[0] += TERMINAL_RETENTION_SECONDS + 1
        self.assertEqual(state.status(job_id).status_code, 404)


class FhirEndpointTests(unittest.TestCase):
    def test_post_then_poll_over_http(self) -> None:
        response = _client.post(_URL, content=_bundle(), headers={"X-API-Key": "k"})
        self.assertEqual(response.status_code, 202)
        location = response.headers["content-location"]
        self.assertIn("/fhir/r4/status/", location)

        path = "/fhir/r4/status/" + _job_id(location)
        statuses = [_client.get(path).status_code for _ in range(3)]
        self.assertEqual(statuses, [202, 202, 200])

    def test_rate_limit_scenario_returns_retry_after(self) -> None:
        response = _client.post(_URL, content=_bundle("mock-429"))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "1")
        self.assertEqual(response.json()["resourceType"], "OperationOutcome")


if __name__ == "__main__":
    unittest.main()
