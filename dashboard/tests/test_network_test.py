"""Unit tests for dashboard.services.network_test.

Socket calls are mocked throughout — no real network access is required.
"""

from __future__ import annotations

import socket
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dashboard.services import network_test

# ---------------------------------------------------------------------------
# validate_host / validate_port
# ---------------------------------------------------------------------------


class TestValidateHost:
    def test_accepts_ip_address(self) -> None:
        assert network_test.validate_host("10.0.0.1") == "10.0.0.1"

    def test_accepts_hostname(self) -> None:
        assert network_test.validate_host("msg.mpi.sit.cymru.nhs.uk") == "msg.mpi.sit.cymru.nhs.uk"

    def test_strips_whitespace(self) -> None:
        assert network_test.validate_host("  example.com  ") == "example.com"

    def test_rejects_empty(self) -> None:
        with pytest.raises(network_test.InvalidTargetError):
            network_test.validate_host("")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(network_test.InvalidTargetError):
            network_test.validate_host("a" * 254)

    def test_rejects_invalid_characters(self) -> None:
        with pytest.raises(network_test.InvalidTargetError):
            network_test.validate_host("example.com; rm -rf /")


class TestValidatePort:
    def test_accepts_valid_port(self) -> None:
        assert network_test.validate_port(2575) == 2575

    def test_accepts_numeric_string(self) -> None:
        assert network_test.validate_port("443") == 443

    def test_rejects_non_numeric(self) -> None:
        with pytest.raises(network_test.InvalidTargetError):
            network_test.validate_port("not-a-port")

    def test_rejects_out_of_range(self) -> None:
        with pytest.raises(network_test.InvalidTargetError):
            network_test.validate_port(70000)

    def test_rejects_zero(self) -> None:
        with pytest.raises(network_test.InvalidTargetError):
            network_test.validate_port(0)


# ---------------------------------------------------------------------------
# resolve_host
# ---------------------------------------------------------------------------


class TestResolveHost:
    def test_returns_addresses_on_success(self) -> None:
        with patch.object(
            network_test.socket, "getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.5", 0))]
        ):
            result = network_test.resolve_host("example.com")

        assert result["resolved"] is True
        assert result["addresses"] == ["10.0.0.5"]

    def test_reports_failure_on_gaierror(self) -> None:
        with patch.object(network_test.socket, "getaddrinfo", side_effect=socket.gaierror("no such host")):
            result = network_test.resolve_host("does-not-exist.invalid")

        assert result["resolved"] is False
        assert result["addresses"] == []
        assert "error" in result

    def test_bounds_a_slow_or_unresponsive_resolver(self) -> None:
        """A DNS server that never answers must not hang the caller indefinitely."""
        released = threading.Event()

        def _slow_getaddrinfo(host: str, port: Any) -> list[Any]:
            released.wait(2.0)  # released below so the background thread doesn't linger past the test
            return [(None, None, None, None, ("10.0.0.5", 0))]

        with patch.object(network_test.socket, "getaddrinfo", side_effect=_slow_getaddrinfo):
            result = network_test.resolve_host("example.com", timeout=0.05)
        released.set()

        assert result["resolved"] is False
        assert "timed out" in result["error"].lower()


# ---------------------------------------------------------------------------
# run_latency_test
# ---------------------------------------------------------------------------


class TestRunLatencyTest:
    def test_raises_for_invalid_host(self) -> None:
        with pytest.raises(network_test.InvalidTargetError):
            network_test.run_latency_test("", 443)

    def test_raises_for_invalid_port(self) -> None:
        with pytest.raises(network_test.InvalidTargetError):
            network_test.run_latency_test("example.com", 99999)

    def test_summarises_successful_attempts(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False

        with (
            patch.object(network_test.socket, "getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.5", 0))]),
            patch.object(network_test.socket, "create_connection", return_value=connection),
        ):
            result = network_test.run_latency_test("example.com", 443, attempts=3)

        assert result["success"] is True
        assert result["success_count"] == 3
        assert result["failure_count"] == 0
        assert result["loss_percent"] == 0.0
        assert result["avg_latency_ms"] is not None

    def test_summarises_failed_attempts(self) -> None:
        with (
            patch.object(network_test.socket, "getaddrinfo", side_effect=socket.gaierror("no such host")),
            patch.object(network_test.socket, "create_connection", side_effect=TimeoutError()),
        ):
            result = network_test.run_latency_test("example.com", 443, attempts=2)

        assert result["success"] is False
        assert result["success_count"] == 0
        assert result["failure_count"] == 2
        assert result["loss_percent"] == 100.0
        assert result["avg_latency_ms"] is None

    def test_reports_connection_refused(self) -> None:
        with (
            patch.object(network_test.socket, "getaddrinfo", return_value=[]),
            patch.object(
                network_test.socket, "create_connection", side_effect=ConnectionRefusedError("refused")
            ),
        ):
            result = network_test.run_latency_test("example.com", 443, attempts=1)

        assert result["attempts"][0]["success"] is False
        assert "refused" in result["attempts"][0]["error"].lower()

    def test_connects_to_the_resolved_address_not_the_hostname(self) -> None:
        """Avoids create_connection repeating (and potentially hanging on) DNS per attempt."""
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False

        with (
            patch.object(network_test.socket, "getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.5", 0))]),
            patch.object(network_test.socket, "create_connection", return_value=connection) as create_connection,
        ):
            network_test.run_latency_test("example.com", 443, attempts=2)

        create_connection.assert_called_with(("10.0.0.5", 443), timeout=network_test.DEFAULT_TIMEOUT_SECONDS)

    def test_skips_connect_attempts_when_dns_resolution_fails(self) -> None:
        """A doomed connect target shouldn't be retried — it would just repeat the same failure."""
        with (
            patch.object(network_test.socket, "getaddrinfo", side_effect=socket.gaierror("no such host")),
            patch.object(network_test.socket, "create_connection") as create_connection,
        ):
            result = network_test.run_latency_test("does-not-exist.invalid", 443, attempts=3)

        create_connection.assert_not_called()
        assert result["failure_count"] == 3
        assert all("no such host" in a["error"] for a in result["attempts"])


# ---------------------------------------------------------------------------
# history persistence (Cosmos-backed)
# ---------------------------------------------------------------------------


def _fake_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "timestamp": 1.0,
        "success": True,
        "avg_latency_ms": 12.3,
        "min_latency_ms": 10.0,
        "max_latency_ms": 15.0,
        "loss_percent": 0.0,
    }
    result.update(overrides)
    return result


class TestHistoryPersistence:
    def test_save_appends_and_get_returns_samples(self) -> None:
        store: dict[str, Any] = {}

        def fake_get(pk: str, doc_id: str) -> dict | None:
            return store.get(doc_id)

        def fake_upsert(pk: str, doc_id: str, data: dict) -> None:
            store[doc_id] = data

        with (
            patch.object(network_test.cosmos_store, "get_document", side_effect=fake_get),
            patch.object(network_test.cosmos_store, "upsert_document", side_effect=fake_upsert),
        ):
            network_test.save_history_sample("example.com", 443, _fake_result())
            history = network_test.get_history("example.com", 443)

        assert history == [
            {
                "timestamp": 1.0,
                "success": True,
                "avg_latency_ms": 12.3,
                "min_latency_ms": 10.0,
                "max_latency_ms": 15.0,
                "loss_percent": 0.0,
            }
        ]

    def test_get_history_returns_empty_when_no_document(self) -> None:
        with patch.object(network_test.cosmos_store, "get_document", return_value=None):
            assert network_test.get_history("example.com", 443) == []

    def test_history_capped_at_max_samples(self) -> None:
        existing_samples = [
            _fake_result(timestamp=float(i)) for i in range(network_test._MAX_HISTORY_SAMPLES)
        ]
        stored: dict[str, Any] = {}

        def fake_get(pk: str, doc_id: str) -> dict | None:
            return {"samples": existing_samples} if doc_id not in stored else stored[doc_id]

        def fake_upsert(pk: str, doc_id: str, data: dict) -> None:
            stored[doc_id] = data

        with (
            patch.object(network_test.cosmos_store, "get_document", side_effect=fake_get),
            patch.object(network_test.cosmos_store, "upsert_document", side_effect=fake_upsert),
        ):
            network_test.save_history_sample("example.com", 443, _fake_result(timestamp=999.0))

        saved_samples = stored["history:example.com:443"]["samples"]
        assert len(saved_samples) == network_test._MAX_HISTORY_SAMPLES
        assert saved_samples[-1]["timestamp"] == 999.0

    def test_delete_history_removes_the_document(self) -> None:
        with patch.object(network_test.cosmos_store, "delete_document") as delete_document:
            network_test.delete_history("example.com", 443)

        delete_document.assert_called_once_with("network-test", "history:example.com:443")

    def test_save_returns_true_when_upsert_succeeds(self) -> None:
        with (
            patch.object(network_test.cosmos_store, "get_document", return_value=None),
            patch.object(network_test.cosmos_store, "upsert_document", return_value=True),
        ):
            assert network_test.save_history_sample("example.com", 443, _fake_result()) is True

    def test_save_returns_false_when_cosmos_is_unreachable(self) -> None:
        """The caller uses this to warn the user without failing the test result itself."""
        with (
            patch.object(network_test.cosmos_store, "get_document", return_value=None),
            patch.object(network_test.cosmos_store, "upsert_document", return_value=False),
        ):
            assert network_test.save_history_sample("example.com", 443, _fake_result()) is False


class TestListTestedEndpoints:
    def test_returns_latest_sample_per_endpoint(self) -> None:
        documents = [
            {
                "host": "a.example.com",
                "port": 443,
                "samples": [_fake_result(timestamp=1.0), _fake_result(timestamp=2.0)],
            },
            {"host": "b.example.com", "port": 22, "samples": [_fake_result(timestamp=5.0)]},
        ]
        with patch.object(network_test.cosmos_store, "query_documents", return_value=documents):
            endpoints = network_test.list_tested_endpoints()

        assert [e["host"] for e in endpoints] == ["b.example.com", "a.example.com"]
        assert endpoints[1]["latest"]["timestamp"] == 2.0

    def test_skips_documents_with_no_samples(self) -> None:
        documents = [{"host": "a.example.com", "port": 443, "samples": []}]
        with patch.object(network_test.cosmos_store, "query_documents", return_value=documents):
            assert network_test.list_tested_endpoints() == []

    def test_returns_empty_when_no_documents(self) -> None:
        with patch.object(network_test.cosmos_store, "query_documents", return_value=[]):
            assert network_test.list_tested_endpoints() == []


# ---------------------------------------------------------------------------
# build_endpoint_options
# ---------------------------------------------------------------------------


class TestBuildEndpointOptions:
    def test_builds_option_per_unique_host_port(self) -> None:
        flows = {
            "phw-to-mpi": {"source": "PHW", "source_host": "phw.internal", "source_port": 2575},
            "paris-to-mpi": {"source": "Paris", "source_host": "paris.internal", "source_port": 2577},
        }
        options = network_test.build_endpoint_options(
            flows, host_key="source_host", port_key="source_port", name_key="source"
        )
        assert len(options) == 2
        assert {o["host"] for o in options} == {"phw.internal", "paris.internal"}

    def test_merges_flows_sharing_the_same_destination(self) -> None:
        flows = {
            "phw-to-mpi": {"destination": "MPI", "destination_host": "mpi.internal", "destination_port": 16005},
            "paris-to-mpi": {"destination": "MPI", "destination_host": "mpi.internal", "destination_port": 16005},
        }
        options = network_test.build_endpoint_options(
            flows, host_key="destination_host", port_key="destination_port", name_key="destination"
        )
        assert len(options) == 1
        assert options[0]["host"] == "mpi.internal"

    def test_skips_flows_missing_host_or_port(self) -> None:
        flows = {
            "phw-to-mpi": {"source": "PHW", "source_host": None, "source_port": 2575},
            "paris-to-mpi": {"source": "Paris", "source_host": "paris.internal", "source_port": None},
        }
        options = network_test.build_endpoint_options(
            flows, host_key="source_host", port_key="source_port", name_key="source"
        )
        assert options == []
