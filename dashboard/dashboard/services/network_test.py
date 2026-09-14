"""Network connectivity testing — TCP connect, DNS resolution, and latency checks.

Used by the "Network Test" dashboard page (see ``network_testing.md``) so support
staff can check connectivity from the dashboard's container (which runs inside the
same Container Apps environment/VNet as the flow servers) to flow source servers,
flow destinations (e.g. MPI), or an arbitrary host:port.

Deliberately implemented with plain ``socket`` calls only — no ``subprocess``/shell
commands and no raw sockets — so it needs no elevated container privileges. This
means real hop-by-hop traceroute is out of scope (see ``network_testing.md``).
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import time
from typing import Any

from dashboard.services import cosmos_store

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_ATTEMPTS = 4

# Cosmos partition + history sizing for latency graphing. This reuses the generic
# document store already used for alarm config/state (see cosmos_store.py) rather
# than introducing a new container.
_HISTORY_PK = "network-test"
_MAX_HISTORY_SAMPLES = 200

_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$")


class InvalidTargetError(ValueError):
    """Raised when a supplied host or port fails validation."""


def validate_host(host: str) -> str:
    """Validate a hostname or IP address, raising InvalidTargetError if malformed.

    Only checks syntactic validity (not reachability) — this is the boundary
    check that keeps the arbitrary-target field from being used to smuggle shell
    metacharacters or absurdly long input through to socket calls.
    """
    host = (host or "").strip()
    if not host:
        raise InvalidTargetError("Host must not be empty")
    if len(host) > 253:
        raise InvalidTargetError("Host is too long")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _HOSTNAME_RE.match(host):
            raise InvalidTargetError(f"'{host}' is not a valid hostname or IP address") from None

    return host


def validate_port(port: Any) -> int:
    """Validate a port number, raising InvalidTargetError if out of range."""
    try:
        port_int = int(port)
    except (TypeError, ValueError) as exc:
        raise InvalidTargetError(f"'{port}' is not a valid port number") from exc

    if not 1 <= port_int <= 65535:
        raise InvalidTargetError(f"Port {port_int} is out of range (1-65535)")

    return port_int


def resolve_host(host: str) -> dict[str, Any]:
    """Resolve a hostname to its IP address(es), timing the lookup."""
    started = time.monotonic()
    try:
        infos = socket.getaddrinfo(host, None)
        addresses = sorted({info[4][0] for info in infos})
        return {
            "resolved": True,
            "addresses": addresses,
            "resolve_time_ms": round((time.monotonic() - started) * 1000, 2),
        }
    except socket.gaierror as exc:
        return {
            "resolved": False,
            "addresses": [],
            "resolve_time_ms": round((time.monotonic() - started) * 1000, 2),
            "error": str(exc),
        }


def _tcp_connect_once(host: str, port: int, timeout: float) -> dict[str, Any]:
    """Attempt a single TCP connect, returning success/failure and latency."""
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"success": True, "latency_ms": round((time.monotonic() - started) * 1000, 2), "error": None}
    except TimeoutError:
        return {"success": False, "latency_ms": None, "error": "Connection timed out"}
    except OSError as exc:
        return {"success": False, "latency_ms": None, "error": str(exc)}


def run_latency_test(
    host: str,
    port: Any,
    attempts: int = DEFAULT_ATTEMPTS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run repeated TCP connect attempts against host:port and summarise latency/loss.

    Raises InvalidTargetError if host/port fail validation — callers should catch
    this and return a 400 rather than letting a malformed target reach socket calls.
    """
    validated_host = validate_host(host)
    validated_port = validate_port(port)

    dns = resolve_host(validated_host)
    attempt_results = [_tcp_connect_once(validated_host, validated_port, timeout) for _ in range(max(1, attempts))]

    latencies = [a["latency_ms"] for a in attempt_results if a["success"]]
    failures = [a for a in attempt_results if not a["success"]]

    return {
        "host": validated_host,
        "port": validated_port,
        "dns": dns,
        "attempts": attempt_results,
        "success_count": len(latencies),
        "failure_count": len(failures),
        "loss_percent": round((len(failures) / len(attempt_results)) * 100, 1) if attempt_results else 0.0,
        "min_latency_ms": round(min(latencies), 2) if latencies else None,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "max_latency_ms": round(max(latencies), 2) if latencies else None,
        "success": bool(latencies),
        "timestamp": time.time(),
    }


def _history_doc_id(host: str, port: int) -> str:
    return f"history:{host}:{port}"


def save_history_sample(host: str, port: int, result: dict[str, Any]) -> None:
    """Append a test result to the endpoint's rolling history (for the latency graph).

    A no-op when Cosmos isn't configured — matches the alarm services' graceful
    degradation behaviour rather than failing the request.
    """
    doc_id = _history_doc_id(host, port)
    existing = cosmos_store.get_document(_HISTORY_PK, doc_id) or {"samples": []}
    samples = existing.get("samples", [])
    samples.append(
        {
            "timestamp": result["timestamp"],
            "success": result["success"],
            "avg_latency_ms": result["avg_latency_ms"],
            "loss_percent": result["loss_percent"],
        }
    )
    samples = samples[-_MAX_HISTORY_SAMPLES:]
    cosmos_store.upsert_document(_HISTORY_PK, doc_id, {"host": host, "port": port, "samples": samples})


def get_history(host: str, port: int) -> list[dict[str, Any]]:
    """Return the rolling history of past test results for an endpoint."""
    doc = cosmos_store.get_document(_HISTORY_PK, _history_doc_id(host, port))
    return (doc or {}).get("samples", [])


def build_endpoint_options(
    flows: dict[str, dict],
    *,
    host_key: str,
    port_key: str,
    name_key: str,
) -> list[dict[str, Any]]:
    """Build deduplicated dropdown options (label, host, port) from flow definitions.

    Flows that share the same host:port (e.g. several flows all deliver to the same
    MPI endpoint) are merged into a single option with a combined label.
    """
    merged: dict[tuple[str, int], list[str]] = {}
    for flow in flows.values():
        host = flow.get(host_key)
        port = flow.get(port_key)
        name = flow.get(name_key)
        if not host or not port:
            continue
        key = (host, int(port))
        names = merged.setdefault(key, [])
        if name and name not in names:
            names.append(name)

    options = [
        {"label": f"{', '.join(names) if names else host} ({host}:{port})", "host": host, "port": port}
        for (host, port), names in merged.items()
    ]
    options.sort(key=lambda option: str(option["label"]))
    return options
