"""Client for the Promptly FHIR ``$process-message`` operation.

Implements the IG's asynchronous pattern: POST the message Bundle, expect ``202 Accepted`` with a
``Content-Location`` status URL, then poll that URL until it returns ``200`` (an OperationOutcome).

Retry policy (applies to the POST and to each status poll):
  - 429: wait for ``Retry-After`` (capped), then retry
  - 5xx / network errors / timeouts: exponential backoff, up to ``max_attempts``
  - 401: one retry with a fresh token when the auth provider supports it, otherwise fail
  - 400 / 403 / 404 / 409 and any other 4xx: never retried
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional, Type
from urllib.parse import urljoin, urlparse

import requests

from fhir_sender.auth import AuthProvider
from fhir_sender.errors import (
    AuthorizationDeliveryError,
    PermanentDeliveryError,
    TransientDeliveryError,
)

logger = logging.getLogger(__name__)

FHIR_JSON = "application/fhir+json"
MAX_DETAIL_LENGTH = 500
ERROR_SEVERITIES = {"error", "fatal"}


class FhirSenderClient:
    def __init__(
        self,
        endpoint_url: str,
        auth: AuthProvider,
        timeout_seconds: int = 30,
        max_attempts: int = 3,
        backoff_seconds: float = 2.0,
        max_retry_after_seconds: float = 60.0,
        poll_interval_seconds: float = 5.0,
        poll_timeout_seconds: float = 120.0,
        allow_insecure_http: bool = False,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        scheme = urlparse(endpoint_url).scheme.lower()
        if scheme != "https" and not (allow_insecure_http and scheme == "http"):
            raise ValueError("FHIR endpoint must use HTTPS")

        self.endpoint_url = endpoint_url
        self._auth = auth
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._max_retry_after_seconds = max_retry_after_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._poll_timeout_seconds = poll_timeout_seconds
        self._session = session or requests.Session()
        self._sleep = sleep
        self._monotonic = monotonic

    def send_bundle(self, bundle_json: str) -> None:
        """Submit a message Bundle and wait for Promptly to finish processing it.

        Raises:
            PermanentDeliveryError: rejected by Promptly; do not retry.
            AuthorizationDeliveryError: credentials rejected.
            TransientDeliveryError: delivery could not be confirmed.
        """
        response = self._request("POST", self.endpoint_url, data=bundle_json.encode("utf-8"))

        if response.status_code == 202:
            self._poll(self._resolve_status_url(response))
        elif response.status_code == 200:
            self._check_outcome(response)
        else:
            self._raise_for_status(response)

    def _resolve_status_url(self, response: requests.Response) -> str:
        location = response.headers.get("Content-Location")
        if not location:
            raise TransientDeliveryError("202 Accepted without a Content-Location status URL")
        status_url = urljoin(self.endpoint_url, location)
        # Credentials are sent to the status URL, so require the configured endpoint's origin.
        endpoint = urlparse(self.endpoint_url)
        status = urlparse(status_url)
        if (status.scheme.lower(), status.netloc.lower()) != (endpoint.scheme.lower(), endpoint.netloc.lower()):
            raise PermanentDeliveryError(202, "Status URL origin differs from the configured endpoint")
        return status_url

    def _poll(self, status_url: str) -> None:
        deadline = self._monotonic() + self._poll_timeout_seconds
        while True:
            response = self._request("GET", status_url, deadline=deadline)
            if response.status_code == 200:
                self._check_outcome(response)
                return
            if response.status_code != 202:
                self._raise_for_status(response)

            delay = self._retry_after_seconds(response) or self._poll_interval_seconds
            delay = min(delay, self._max_retry_after_seconds)
            if self._monotonic() + delay > deadline:
                raise TransientDeliveryError(
                    f"Processing not complete after {self._poll_timeout_seconds:.0f}s "
                    f"(X-Progress: {response.headers.get('X-Progress', 'n/a')})"
                )
            logger.debug("Message still processing; polling again in %.1fs", delay)
            self._sleep(delay)

    def _request(
        self, method: str, url: str, data: Optional[bytes] = None, deadline: Optional[float] = None
    ) -> requests.Response:
        """Send with retries; a deadline (monotonic seconds) bounds timeouts and waits so polling cannot overrun."""
        last_error = "no attempts made"
        token_refreshed = False
        attempt = 1
        while attempt <= self._max_attempts:
            timeout: float = self._timeout_seconds
            if deadline is not None:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise TransientDeliveryError(
                        f"Polling deadline reached before {method} could complete: {last_error}"
                    )
                timeout = min(timeout, remaining)
            headers = {"Accept": FHIR_JSON, **self._auth.headers()}
            if data is not None:
                headers["Content-Type"] = FHIR_JSON

            try:
                response = self._session.request(
                    method, url, data=data, headers=headers,
                    timeout=timeout, allow_redirects=False,
                )
            except requests.exceptions.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("%s %s failed (attempt %d/%d): %s", method, url, attempt, self._max_attempts, last_error)
                self._backoff(attempt, deadline)
                attempt += 1
                continue

            status = response.status_code
            if status == 401 and not token_refreshed and self._auth.invalidate():
                token_refreshed = True
                logger.warning("Received 401; retrying once with fresh credentials")
                continue
            if status == 429:
                last_error = "HTTP 429 Too Many Requests"
                delay = self._retry_after_seconds(response) or self._backoff_delay(attempt)
                logger.warning("Rate limited (attempt %d/%d); waiting %.1fs", attempt, self._max_attempts, delay)
                if attempt < self._max_attempts:
                    self._wait(min(delay, self._max_retry_after_seconds), deadline)
                attempt += 1
                continue
            if status >= 500:
                last_error = f"HTTP {status}: {_summarise_outcome(response)}"
                logger.warning("%s %s returned %d (attempt %d/%d)", method, url, status, attempt, self._max_attempts)
                self._backoff(attempt, deadline)
                attempt += 1
                continue
            return response

        raise TransientDeliveryError(f"{method} failed after {self._max_attempts} attempt(s): {last_error}")

    def _backoff_delay(self, attempt: int) -> float:
        return self._backoff_seconds * (2 ** (attempt - 1))

    def _backoff(self, attempt: int, deadline: Optional[float] = None) -> None:
        if attempt < self._max_attempts:
            self._wait(self._backoff_delay(attempt), deadline)

    def _wait(self, delay: float, deadline: Optional[float]) -> None:
        if deadline is not None and self._monotonic() + delay >= deadline:
            raise TransientDeliveryError("Polling deadline would be exceeded while waiting to retry")
        self._sleep(delay)

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            seconds = float(value)
        except ValueError:
            return None  # HTTP-date form is not used by Promptly per the IG
        return seconds if seconds > 0 else None

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        status = response.status_code
        detail = _summarise_outcome(response)
        if status in (401, 403):
            raise AuthorizationDeliveryError(status, detail)
        raise PermanentDeliveryError(status, detail)

    @staticmethod
    def _check_outcome(response: requests.Response) -> None:
        """A 200 only means the status call succeeded; the OperationOutcome says whether processing did."""
        try:
            body = response.json()
        except ValueError as exc:
            raise TransientDeliveryError("200 response did not contain a valid OperationOutcome") from exc
        if not isinstance(body, dict) or body.get("resourceType") != "OperationOutcome":
            raise TransientDeliveryError("200 response did not contain an OperationOutcome")
        issues = body.get("issue") or []
        if any(isinstance(i, dict) and i.get("severity") in ERROR_SEVERITIES for i in issues):
            raise PermanentDeliveryError(response.status_code, _summarise_outcome(response))

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "FhirSenderClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        self.close()


def _summarise_outcome(response: requests.Response) -> str:
    """Condense an OperationOutcome (or raw body) into a short log-safe string."""
    try:
        body = response.json()
    except ValueError:
        return (response.text or response.reason or "no body")[:MAX_DETAIL_LENGTH]

    parts: list[str] = []
    issues = body.get("issue", []) if isinstance(body, dict) else []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        text = (issue.get("details") or {}).get("text") or issue.get("diagnostics") or ""
        parts.append(f"{issue.get('severity', '?')}/{issue.get('code', '?')}: {text}".strip())
    summary = "; ".join(parts) if parts else json.dumps(body)
    return summary[:MAX_DETAIL_LENGTH]
