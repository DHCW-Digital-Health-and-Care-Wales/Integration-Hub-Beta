"""Mock of the Promptly ``$process-message`` asynchronous API (WPAS-Promptly IG), for local sender testing.

Behaviour is driven by ``Bundle.id`` so a tester can trigger each scenario from the Bundle itself:

  (any other id)    accepted, 2 polls "Processing", then 200 success
  mock-slow         accepted, 6 polls before success
  mock-error-outcome accepted, then 200 with an error OperationOutcome
  mock-status-400   accepted, then the status poll returns 400
  mock-400 / -401 / -403 / -404 / -409 / -429 / -500
                    the POST is rejected with that status (429 includes Retry-After)
  mock-429-once / mock-500-once
                    the first POST for that id fails, the retry is accepted

Terminal status responses are kept for 5 minutes so repeated status GETs return the same outcome.
State is held in memory and is lost when the mock restarts.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

STATUS_PATH = "/fhir/r4/status"
SCENARIO_PREFIX = "mock-"
DEFAULT_POLLS = 2
SLOW_POLLS = 6
RETRY_AFTER_SECONDS = "1"
TERMINAL_RETENTION_SECONDS = 300

IMMEDIATE_FAILURES = {"400", "401", "403", "404", "409", "429", "500"}
FAIL_ONCE = {"429-once": 429, "500-once": 500}


@dataclass
class MockResponse:
    status_code: int
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class _Job:
    polls_remaining: int
    final: MockResponse
    completed_at: float | None = None


def operation_outcome(severity: str, code: str, text: str) -> dict[str, Any]:
    return {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": severity, "code": code, "details": {"text": text}}],
    }


class FhirMockState:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._jobs: dict[str, _Job] = {}
        self._failed_once: set[str] = set()
        self._clock = clock

    def submit(self, raw_body: str, base_url: str) -> MockResponse:
        self._purge_expired()
        try:
            bundle = json.loads(raw_body)
        except ValueError:
            return MockResponse(400, operation_outcome("error", "invalid", "Body is not valid JSON"))
        if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle" or bundle.get("type") != "message":
            return MockResponse(400, operation_outcome("error", "invalid", "Expected a Bundle of type 'message'"))

        bundle_id = str(bundle.get("id", ""))
        scenario = bundle_id[len(SCENARIO_PREFIX):] if bundle_id.startswith(SCENARIO_PREFIX) else ""

        failure = self._submit_failure(bundle_id, scenario)
        if failure:
            return failure

        job_id = uuid.uuid4().hex
        self._jobs[job_id] = _Job(SLOW_POLLS if scenario == "slow" else DEFAULT_POLLS, _final_response(scenario))
        return MockResponse(202, headers={"Content-Location": f"{base_url.rstrip('/')}{STATUS_PATH}/{job_id}"})

    def status(self, job_id: str) -> MockResponse:
        self._purge_expired()
        job = self._jobs.get(job_id)
        if job is None:
            return MockResponse(404, operation_outcome("error", "not-found", "Unknown status id"))
        if job.polls_remaining > 0:
            job.polls_remaining -= 1
            return MockResponse(202, headers={"X-Progress": "Processing", "Retry-After": RETRY_AFTER_SECONDS})
        # Keep the terminal response so a sender retrying a GET after a dropped connection sees the same outcome.
        if job.completed_at is None:
            job.completed_at = self._clock()
        return job.final

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [
            job_id for job_id, job in self._jobs.items()
            if job.completed_at is not None and now - job.completed_at > TERMINAL_RETENTION_SECONDS
        ]
        for job_id in expired:
            del self._jobs[job_id]

    def _submit_failure(self, bundle_id: str, scenario: str) -> MockResponse | None:
        if scenario in IMMEDIATE_FAILURES:
            status = int(scenario)
            headers = {"Retry-After": RETRY_AFTER_SECONDS} if status == 429 else {}
            return MockResponse(status, operation_outcome("error", "processing", f"Mock {status} response"), headers)
        if scenario in FAIL_ONCE and bundle_id not in self._failed_once:
            self._failed_once.add(bundle_id)
            status = FAIL_ONCE[scenario]
            headers = {"Retry-After": RETRY_AFTER_SECONDS} if status == 429 else {}
            outcome = operation_outcome("error", "processing", f"Mock {status} (first attempt)")
            return MockResponse(status, outcome, headers)
        return None


def _final_response(scenario: str) -> MockResponse:
    if scenario == "status-400":
        return MockResponse(400, operation_outcome("error", "invalid", "Invalid message format"))
    if scenario == "error-outcome":
        return MockResponse(200, operation_outcome("error", "business-rule", "Patient could not be matched"))
    return MockResponse(200, operation_outcome("information", "informational", "Message processed successfully"))
