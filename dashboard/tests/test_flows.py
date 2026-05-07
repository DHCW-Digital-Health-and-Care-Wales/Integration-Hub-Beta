"""
Unit tests for flow health calculation logic.
Pure logic — no Azure calls, no mocking needed.
"""
from __future__ import annotations

from dashboard.services.flows import _FLOW_DEFS, flow_health, overall_health, queue_health

# Test flows with hardcoded queue names - independent of config.py
TEST_FLOWS = {
    "phw-to-mpi": {
        "label": "PHW → MPI",
        "source": "PHW",
        "source_port": 2575,
        "pre_queue": "pre-phw-transform",
        "transformer": "PHW Transformer",
        "post_queue": "post-phw-transform",
        "destination": "MPI",
        "colour": "#3b82f6",
        "icon": "bi-heart-pulse",
    },
}


class TestQueueHealth:
    def test_healthy_when_empty(self) -> None:
        assert queue_health(0, 0) == "healthy"

    def test_healthy_below_warning(self) -> None:
        assert queue_health(9, 0) == "healthy"

    def test_warning_at_threshold(self) -> None:
        assert queue_health(10, 0) == "warning"

    def test_warning_with_dlq(self) -> None:
        assert queue_health(0, 1) == "warning"

    def test_critical_at_threshold(self) -> None:
        assert queue_health(50, 0) == "critical"

    def test_critical_overrides_dlq(self) -> None:
        assert queue_health(50, 5) == "critical"


class TestFlowHealth:
    def _make_queue(self, name: str, active: int = 0, dlq: int = 0) -> dict:
        return {"name": name, "active_message_count": active, "dead_letter_message_count": dlq}

    def test_healthy_when_all_queues_empty(self) -> None:
        queues_by_name = {
            "pre-phw-transform":  self._make_queue("pre-phw-transform"),
            "post-phw-transform": self._make_queue("post-phw-transform"),
        }
        assert flow_health("phw-to-mpi", queues_by_name, TEST_FLOWS) == "healthy"

    def test_warning_when_pre_queue_at_threshold(self) -> None:
        queues_by_name = {
            "pre-phw-transform":  self._make_queue("pre-phw-transform", active=15),
            "post-phw-transform": self._make_queue("post-phw-transform"),
        }
        assert flow_health("phw-to-mpi", queues_by_name, TEST_FLOWS) == "warning"

    def test_critical_when_post_queue_critical(self) -> None:
        queues_by_name = {
            "pre-phw-transform":  self._make_queue("pre-phw-transform"),
            "post-phw-transform": self._make_queue("post-phw-transform", active=50),
        }
        assert flow_health("phw-to-mpi", queues_by_name, TEST_FLOWS) == "critical"

    def test_unknown_when_no_queues_found(self) -> None:
        assert flow_health("phw-to-mpi", {}, TEST_FLOWS) == "unknown"

    def test_all_flows_defined(self) -> None:
        expected = {"phw-to-mpi", "paris-to-mpi", "chemocare-to-mpi", "pims-to-mpi", "wds-to-mpi", "mpi-outbound"}
        assert {d["id"] for d in _FLOW_DEFS} == expected


class TestOverallHealth:
    def test_healthy_when_all_healthy(self) -> None:
        assert overall_health(["healthy", "healthy", "healthy"]) == "healthy"

    def test_warning_when_any_warning(self) -> None:
        assert overall_health(["healthy", "warning", "healthy"]) == "warning"

    def test_critical_when_any_critical(self) -> None:
        assert overall_health(["healthy", "warning", "critical"]) == "critical"

    def test_critical_takes_precedence(self) -> None:
        assert overall_health(["critical", "warning", "healthy"]) == "critical"

    def test_unknown_with_mixed_unknown(self) -> None:
        assert overall_health(["healthy", "unknown"]) == "unknown"
