"""
Unit tests for flow health calculation logic.
Pure logic — no Azure calls, no mocking needed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from dashboard.services.flows import (
    _FLOW_DEFS,
    _merge_subscription_records,
    build_flow_data,
    flow_health,
    overall_health,
    queue_health,
)

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

# Patch config thresholds to known values so tests are env-independent
_THRESHOLD_KWARGS: dict[str, int] = {
    "QUEUE_WARNING_THRESHOLD": 10,
    "QUEUE_CRITICAL_THRESHOLD": 50,
    "DLQ_WARNING_THRESHOLD": 1,
}


class TestQueueHealth:
    def test_healthy_when_empty(self) -> None:
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert queue_health(0, 0) == "healthy"

    def test_healthy_below_warning(self) -> None:
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert queue_health(9, 0) == "healthy"

    def test_warning_at_threshold(self) -> None:
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert queue_health(10, 0) == "warning"

    def test_warning_with_dlq(self) -> None:
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert queue_health(0, 1) == "warning"

    def test_critical_at_threshold(self) -> None:
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert queue_health(50, 0) == "critical"

    def test_critical_overrides_dlq(self) -> None:
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert queue_health(50, 5) == "critical"


class TestFlowHealth:
    def _make_queue(self, name: str, active: int = 0, dlq: int = 0) -> dict:
        return {"name": name, "active_message_count": active, "dead_letter_message_count": dlq}

    def test_healthy_when_all_queues_empty(self) -> None:
        queues_by_name = {
            "pre-phw-transform": self._make_queue("pre-phw-transform"),
            "post-phw-transform": self._make_queue("post-phw-transform"),
        }
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert flow_health("phw-to-mpi", queues_by_name, TEST_FLOWS) == "healthy"

    def test_warning_when_pre_queue_at_threshold(self) -> None:
        queues_by_name = {
            "pre-phw-transform": self._make_queue("pre-phw-transform", active=15),
            "post-phw-transform": self._make_queue("post-phw-transform"),
        }
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert flow_health("phw-to-mpi", queues_by_name, TEST_FLOWS) == "warning"

    def test_critical_when_post_queue_critical(self) -> None:
        queues_by_name = {
            "pre-phw-transform": self._make_queue("pre-phw-transform"),
            "post-phw-transform": self._make_queue("post-phw-transform", active=50),
        }
        assert flow_health("phw-to-mpi", queues_by_name, TEST_FLOWS) == "critical"

    def test_unknown_when_no_queues_found(self) -> None:
        assert flow_health("phw-to-mpi", {}, TEST_FLOWS) == "unknown"

    def test_hybrid_topic_to_queue_flow_uses_subscription_and_post_queue_health(self) -> None:
        flows: dict[str, dict[str, Any]] = {
            "wds-to-wis": {
                "label": "WDS → WIS",
                "source": "WDS",
                "source_port": None,
                "pre_queue": None,
                "transformer": "WDS Transformer",
                "post_queue": "post-wis-sender",
                "topic": "topic-wds-input",
                "subscriptions": [
                    {
                        "name": "sub-wds-wis-transformer",
                        "active_message_count": 0,
                        "dead_letter_message_count": 0,
                    }
                ],
                "destination": "WIS",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }
        queues_by_name = {
            "post-wis-sender": self._make_queue("post-wis-sender", dlq=1),
        }

        assert flow_health("wds-to-wis", queues_by_name, flows) == "warning"

    def test_hybrid_topic_to_queue_flow_is_unknown_when_subscription_status_is_unknown(self) -> None:
        flows = {
            "wds-to-wis": {
                "label": "WDS → WIS",
                "source": "WDS",
                "source_port": None,
                "pre_queue": None,
                "transformer": "WDS Transformer",
                "post_queue": "post-wis-sender",
                "topic": "topic-wds-input",
                "subscriptions": [
                    {
                        "name": "sub-wds-wis-transformer",
                        "status": "Unknown",
                        "active_message_count": 0,
                        "dead_letter_message_count": 0,
                    }
                ],
                "destination": "WIS",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }
        queues_by_name = {
            "post-wis-sender": self._make_queue("post-wis-sender"),
        }

        assert flow_health("wds-to-wis", queues_by_name, flows) == "unknown"

    def test_topic_backlog_drives_flow_health(self) -> None:
        flows = {
            "mpi-to-topic": {
                "label": "MPI Outbound",
                "source": "MPI",
                "source_port": 2580,
                "pre_queue": None,
                "transformer": None,
                "post_queue": None,
                "topic": "topic-wds-input",
                "subscriptions": [
                    {
                        "name": "sub-outbound",
                        "status": "Active",
                        "active_message_count": 0,
                        "dead_letter_message_count": 0,
                    }
                ],
                "destination": "Downstream Systems",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }
        queues_by_name: dict[str, dict] = {}
        topics_by_name = {
            "topic-wds-input": {
                "name": "topic-wds-input",
                "active_message_count": 60,
                "dead_letter_message_count": 0,
            }
        }
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert flow_health("mpi-to-topic", queues_by_name, flows, topics_by_name) == "critical"

    def test_topic_dead_letters_drive_flow_health(self) -> None:
        flows = {
            "mpi-to-topic": {
                "label": "MPI Outbound",
                "source": "MPI",
                "source_port": 2580,
                "pre_queue": None,
                "transformer": None,
                "post_queue": None,
                "topic": "topic-wds-input",
                "subscriptions": [
                    {
                        "name": "sub-outbound",
                        "status": "Active",
                        "active_message_count": 0,
                        "dead_letter_message_count": 0,
                    }
                ],
                "destination": "Downstream Systems",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }
        queues_by_name: dict[str, dict] = {}
        topics_by_name = {
            "topic-wds-input": {
                "name": "topic-wds-input",
                "active_message_count": 0,
                "dead_letter_message_count": 3,
            }
        }
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            assert flow_health("mpi-to-topic", queues_by_name, flows, topics_by_name) == "warning"

    def test_missing_publisher_topic_is_unknown_when_snapshot_was_supplied(self) -> None:
        flows = {
            "mpi-to-topic": {
                "label": "MPI Outbound",
                "source": "MPI",
                "source_port": 2580,
                "pre_queue": None,
                "transformer": None,
                "post_queue": None,
                "topic": "topic-wds-input",
                "subscriptions": [
                    {
                        "name": "sub-outbound",
                        "status": "Active",
                        "active_message_count": 0,
                        "dead_letter_message_count": 0,
                    }
                ],
                "destination": "Downstream Systems",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }

        assert flow_health("mpi-to-topic", {}, flows, {}) == "unknown"

    def test_missing_queue_stage_is_unknown_when_queue_is_absent(self) -> None:
        flows = {
            "wds-to-wis": {
                "label": "WDS → WIS",
                "source": "WDS",
                "source_port": None,
                "pre_queue": None,
                "transformer": "WDS Transformer",
                "post_queue": "post-wis-sender",
                "topic": "topic-wds-input",
                "subscriptions": [
                    {
                        "name": "sub-wds-wis-transformer",
                        "status": "Active",
                        "active_message_count": 0,
                        "dead_letter_message_count": 0,
                    }
                ],
                "destination": "WIS",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }

        assert flow_health("wds-to-wis", {}, flows) == "unknown"

    def test_all_flows_defined(self) -> None:
        expected = {
            "phw-to-mpi",
            "paris-to-mpi",
            "mosaiq-to-mpi",
            "chemocare-to-mpi",
            "pims-to-mpi",
            "wds-to-mpi",
            "mpi-outbound",
        }
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


class TestBuildFlowData:
    def test_subscription_consumer_metadata_is_retained(self) -> None:
        flows = {
            "mpi-to-topic": {
                "label": "MPI Outbound",
                "source": "MPI",
                "source_port": 2580,
                "pre_queue": None,
                "transformer": None,
                "post_queue": None,
                "topic": "prefix-sbt-mpi-hl7-input",
                "subscriptions": [
                    {
                        "name": "prefix-sbs-outbound",
                        "topic": "prefix-sbt-mpi-hl7-input",
                        "status": "Active",
                        "message_count": 8,
                        "active_message_count": 4,
                        "dead_letter_message_count": 1,
                        "consumer_apps": [
                            {
                                "app_name": "mpi-phw-sender-ca",
                                "microservice_id": "mpi_phw_sender",
                                "sender_type": "subscription_sender",
                                "workflow_id": "mpi-to-topic",
                            }
                        ],
                    }
                ],
                "destination": "Downstream Systems",
                "colour": "#f59e0b",
                "icon": "bi-broadcast",
            }
        }

        result = build_flow_data([], flows)

        assert result[0]["subscriptions"][0]["entity_name"] == "prefix-sbt-mpi-hl7-input/prefix-sbs-outbound"
        assert result[0]["subscriptions"][0]["consumer_apps"][0]["app_name"] == "mpi-phw-sender-ca"

    def test_topic_summary_is_populated_from_topics(self) -> None:
        flows = {
            "mpi-to-topic": {
                "label": "MPI Outbound",
                "source": "MPI",
                "source_port": 2580,
                "pre_queue": None,
                "transformer": None,
                "post_queue": None,
                "topic": "topic-wds-input",
                "subscriptions": [],
                "destination": "Downstream Systems",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }
        topics = [
            {
                "name": "topic-wds-input",
                "active_message_count": 7,
                "dead_letter_message_count": 2,
            }
        ]
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            result = build_flow_data([], flows, topics)

        topic_summary = result[0]["topic_summary"]
        assert topic_summary["exists"] is True
        assert topic_summary["active"] == 7
        assert topic_summary["dlq"] == 2
        assert topic_summary["health"] == "warning"
        assert result[0]["health"] == "warning"

    def test_shared_topic_backlog_ignored_for_consumer_flow(self) -> None:
        """A flow that consumes (but does not publish to) a shared topic must
        not have the topic's own backlog counted against it — that belongs to
        the owning/publishing flow."""
        flows: dict[str, dict[str, Any]] = {
            "wds-to-wis": {
                "label": "WDS → WIS",
                "source": "WDS",
                "source_port": None,
                "pre_queue": None,
                "transformer": "WDS Transformer",
                "post_queue": "post-wis-sender",
                "topic": "topic-wds-input",
                "subscriptions": [],
                "destination": "WIS",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }
        topics = [
            {
                "name": "topic-wds-input",
                "active_message_count": 7,
                "dead_letter_message_count": 2,
            }
        ]
        queues = [
            {
                "name": "post-wis-sender",
                "active_message_count": 0,
                "dead_letter_message_count": 0,
            }
        ]
        with patch.multiple(
            "dashboard.services.flows.config",
            QUEUE_WARNING_THRESHOLD=10,
            QUEUE_CRITICAL_THRESHOLD=50,
            DLQ_WARNING_THRESHOLD=1,
        ):
            result = build_flow_data(queues, flows, topics)

        topic_summary = result[0]["topic_summary"]
        assert topic_summary["exists"] is False
        assert topic_summary["active"] == 0
        assert topic_summary["dlq"] == 0
        # Consumer flow judged only on its own queue backlog — the shared
        # topic's backlog (which would be 'warning') must not leak in.
        assert result[0]["health"] == "healthy"

    def test_topic_summary_defaults_when_no_topic(self) -> None:
        result = build_flow_data([], TEST_FLOWS)

        topic_summary = result[0]["topic_summary"]
        assert topic_summary["exists"] is False
        assert topic_summary["active"] == 0
        assert topic_summary["dlq"] == 0

    def test_snapshot_subscriptions_refresh_flow_counts(self) -> None:
        flows = {
            "mpi-to-topic": {
                "label": "MPI Outbound",
                "source": "MPI",
                "source_port": 2580,
                "pre_queue": None,
                "transformer": None,
                "post_queue": None,
                "topic": "topic-wds-input",
                "subscriptions": [
                    {
                        "name": "sub-outbound",
                        "topic": "topic-wds-input",
                        "status": "Active",
                        "message_count": 0,
                        "active_message_count": 0,
                        "dead_letter_message_count": 0,
                        "consumer_apps": [{"app_name": "sender-ca", "microservice_id": "sender"}],
                    }
                ],
                "destination": "Downstream Systems",
                "colour": "#0ea5e9",
                "icon": "bi-send",
            }
        }
        topics = [
            {
                "name": "topic-wds-input",
                "active_message_count": 0,
                "dead_letter_message_count": 0,
                "subscriptions": [
                    {
                        "name": "sub-outbound",
                        "topic": "topic-wds-input",
                        "status": "Active",
                        "message_count": 9,
                        "active_message_count": 7,
                        "dead_letter_message_count": 2,
                        "consumer_apps": [{"app_name": "sender-ca", "microservice_id": "sender"}],
                    }
                ],
            }
        ]

        result = build_flow_data([], flows, topics)

        assert result[0]["subscriptions"][0]["active"] == 7
        assert result[0]["subscriptions"][0]["dlq"] == 2


class TestMergeSubscriptionRecords:
    """A topic can be shared by several flows; enrichment must only retain the
    subscriptions that discovery attributed to *this* flow."""

    TOPIC = "topic-wds-input"
    OWNED = "sbs-wds-mpi-sender"
    OTHER = "sbs-wds-wis-transformer"

    def test_foreign_subscription_on_shared_topic_is_not_imported(self) -> None:
        flow_subscriptions = [{"name": self.OWNED}]
        # Service Bus returns *every* subscription on the shared topic.
        service_bus_subscriptions = [
            {"name": self.OWNED, "status": "Active", "active_message_count": 3, "dead_letter_message_count": 0},
            {"name": self.OTHER, "status": "Active", "active_message_count": 9, "dead_letter_message_count": 1},
        ]

        merged = _merge_subscription_records(self.TOPIC, flow_subscriptions, [], service_bus_subscriptions)

        names = {sub["name"] for sub in merged}
        assert names == {self.OWNED}, "foreign subscription leaked into this flow"

    def test_owned_subscription_is_enriched_with_live_counts(self) -> None:
        flow_subscriptions = [{"name": self.OWNED}]
        service_bus_subscriptions = [
            {"name": self.OWNED, "status": "Active", "active_message_count": 3, "dead_letter_message_count": 2},
        ]

        merged = _merge_subscription_records(self.TOPIC, flow_subscriptions, [], service_bus_subscriptions)

        assert len(merged) == 1
        sub = merged[0]
        assert sub["name"] == self.OWNED
        assert sub["active_message_count"] == 3
        assert sub["dead_letter_message_count"] == 2
        assert sub["entity_name"] == f"{self.TOPIC}/{self.OWNED}"

    def test_no_owned_subscriptions_returns_empty(self) -> None:
        service_bus_subscriptions = [
            {"name": self.OTHER, "status": "Active", "active_message_count": 9, "dead_letter_message_count": 1},
        ]

        merged = _merge_subscription_records(self.TOPIC, [], [], service_bus_subscriptions)

        assert merged == []
