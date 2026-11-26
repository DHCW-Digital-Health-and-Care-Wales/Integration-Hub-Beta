"""Endpoint connectivity tester and NHS Wales Integration Hub local presets."""
from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request

from ultra7.models import Endpoint

_ALLOWED_SCHEMES = {"http", "https"}

INTEGRATION_HUB_PRESETS: tuple[tuple[str, Endpoint], ...] = (
    ("PHW → MPI (MLLP :2575)", Endpoint(kind="mllp", host="127.0.0.1", port=2575, timeout_seconds=5.0)),
    ("CAV Paris → MPI (MLLP :2577)", Endpoint(kind="mllp", host="127.0.0.1", port=2577, timeout_seconds=5.0)),
    ("ChemoCare → MPI (MLLP :2578)", Endpoint(kind="mllp", host="127.0.0.1", port=2578, timeout_seconds=5.0)),
    ("PIMS → MPI (MLLP :2579)", Endpoint(kind="mllp", host="127.0.0.1", port=2579, timeout_seconds=5.0)),
    ("Mosaiq → MPI (MLLP :2583)", Endpoint(kind="mllp", host="127.0.0.1", port=2583, timeout_seconds=5.0)),
    ("Ultra7 Mock MLLP (:2599)", Endpoint(kind="mllp", host="127.0.0.1", port=2599, timeout_seconds=5.0)),
    (
        "Ultra7 Mock HTTP (:8090)",
        Endpoint(kind="rest", url="http://127.0.0.1:8090/ingest", timeout_seconds=5.0),
    ),
)


def test_endpoint_connection(endpoint: Endpoint) -> tuple[bool, float, str]:
    """Verify reachability of *endpoint*. Returns ``(ok, latency_ms, detail)``."""
    if endpoint.kind == "mllp":
        if not endpoint.host or not endpoint.port:
            return False, 0.0, "Host and port are required"
        start = time.monotonic()
        try:
            with socket.create_connection((endpoint.host, endpoint.port), timeout=endpoint.timeout_seconds):
                pass
        except (OSError, TimeoutError) as exc:
            return False, (time.monotonic() - start) * 1000, str(exc)
        return True, (time.monotonic() - start) * 1000, f"TCP connected to {endpoint.host}:{endpoint.port}"

    if not endpoint.url:
        return False, 0.0, "URL is required"
    scheme = endpoint.url.split("://", 1)[0].lower()
    if scheme not in _ALLOWED_SCHEMES:
        return False, 0.0, f"Unsupported URL scheme: {scheme}"

    request = urllib.request.Request(endpoint.url, headers=dict(endpoint.headers), method="HEAD")
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=endpoint.timeout_seconds) as response:  # noqa: S310  # nosec B310
            return True, (time.monotonic() - start) * 1000, f"HTTP {response.status} reachable"
    except urllib.error.HTTPError as exc:
        # An HTTP response (e.g. 405 Method Not Allowed on HEAD) still confirms the endpoint is reachable.
        return True, (time.monotonic() - start) * 1000, f"Reachable (HTTP {exc.code})"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, (time.monotonic() - start) * 1000, str(exc)
