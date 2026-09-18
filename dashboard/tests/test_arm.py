"""
Unit tests for Container App discovery (arm.py).
Tests the classification and flow-building logic — no Azure calls.
"""

from __future__ import annotations

from typing import Any

from dashboard.services.arm import _build_flow, _classify_app, _merge_subscription_sender_flows


class TestClassifyApp:
    def test_server_with_egress_queue(self) -> None:
        env = {"EGRESS_QUEUE_NAME": "some-queue", "WORKFLOW_ID": "phw-to-mpi"}
        assert _classify_app(env) == "server"

    def test_server_with_egress_topic(self) -> None:
        env = {"EGRESS_TOPIC_NAME": "some-topic", "WORKFLOW_ID": "mpi-to-topic"}
        assert _classify_app(env) == "server"

    def test_transformer(self) -> None:
        env = {
            "INGRESS_QUEUE_NAME": "pre-q",
            "EGRESS_QUEUE_NAME": "post-q",
            "WORKFLOW_ID": "phw-to-mpi",
        }
        assert _classify_app(env) == "transformer"

    def test_sender(self) -> None:
        env = {"INGRESS_QUEUE_NAME": "post-q", "WORKFLOW_ID": "phw-to-mpi"}
        assert _classify_app(env) == "sender"

    def test_subscription_sender(self) -> None:
        env = {
            "INGRESS_TOPIC_NAME": "some-topic",
            "INGRESS_SUBSCRIPTION_NAME": "some-sub",
            "WORKFLOW_ID": "mpi-to-topic",
        }
        assert _classify_app(env) == "subscription_sender"

    def test_unknown_no_relevant_vars(self) -> None:
        env = {"WORKFLOW_ID": "mystery"}
        assert _classify_app(env) == "unknown"


class TestBuildFlow:
    def test_standard_flow_with_transformer(self) -> None:
        apps: list[dict[str, Any]] = [
            {
                "name": "phw-hl7server-ca",
                "env": {
                    "WORKFLOW_ID": "phw-to-mpi",
                    "EGRESS_QUEUE_NAME": "prefix-sbq-phw-hl7-transformer",
                },
                "target_port": 2575,
            },
            {
                "name": "phw-hl7transformer-ca",
                "env": {
                    "WORKFLOW_ID": "phw-to-mpi",
                    "INGRESS_QUEUE_NAME": "prefix-sbq-phw-hl7-transformer",
                    "EGRESS_QUEUE_NAME": "prefix-sbq-hl7-sender",
                    "MICROSERVICE_ID": "phw_transformer",
                },
                "target_port": None,
            },
            {
                "name": "hl7sender-ca",
                "env": {
                    "WORKFLOW_ID": "phw-to-mpi",
                    "INGRESS_QUEUE_NAME": "prefix-sbq-hl7-sender",
                },
                "target_port": None,
            },
        ]
        flow = _build_flow("phw-to-mpi", apps)

        assert flow["label"] == "PHW → MPI"
        assert flow["source"] == "PHW"
        assert flow["source_port"] == 2575
        assert flow["pre_queue"] == "prefix-sbq-phw-hl7-transformer"
        assert flow["post_queue"] == "prefix-sbq-hl7-sender"
        assert flow["transformer"] == "PHW Transformer"
        assert flow["topic"] is None
        assert flow["destination"] == "MPI"

    def test_flow_without_transformer(self) -> None:
        apps: list[dict[str, Any]] = [
            {
                "name": "paris-hl7server-ca",
                "env": {
                    "WORKFLOW_ID": "paris-to-mpi",
                    "EGRESS_QUEUE_NAME": "prefix-sbq-paris-sender",
                },
                "target_port": 2577,
            },
            {
                "name": "paris-sender-ca",
                "env": {
                    "WORKFLOW_ID": "paris-to-mpi",
                    "INGRESS_QUEUE_NAME": "prefix-sbq-paris-sender",
                },
                "target_port": None,
            },
        ]
        flow = _build_flow("paris-to-mpi", apps)

        assert flow["pre_queue"] is None
        assert flow["post_queue"] == "prefix-sbq-paris-sender"
        assert flow["transformer"] is None
        assert flow["source_port"] == 2577

    def test_topic_based_flow(self) -> None:
        apps: list[dict[str, Any]] = [
            {
                "name": "mpi-hl7server-ca",
                "env": {
                    "WORKFLOW_ID": "mpi-to-topic",
                    "EGRESS_TOPIC_NAME": "prefix-sbt-mpi-hl7-input",
                },
                "target_port": 2580,
            },
            {
                "name": "mpi-phw-sender-ca",
                "env": {
                    "WORKFLOW_ID": "mpi-to-topic",
                    "INGRESS_TOPIC_NAME": "prefix-sbt-mpi-hl7-input",
                    "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-mpi-phw-sender",
                },
                "target_port": None,
            },
        ]
        flow = _build_flow("mpi-to-topic", apps)

        assert flow["topic"] == "prefix-sbt-mpi-hl7-input"
        assert flow["pre_queue"] is None
        assert flow["post_queue"] is None
        assert flow["label"] == "MPI Outbound"
        assert flow["source_port"] == 2580
        assert flow["subscriptions"][0]["name"] == "prefix-sbs-mpi-phw-sender"
        assert flow["subscriptions"][0]["consumer_apps"][0]["app_name"] == "mpi-phw-sender-ca"

    def test_merge_subscription_sender_flow_keeps_consumer_metadata(self) -> None:
        flows = {
            "mpi-to-topic": {
                "topic": "prefix-sbt-mpi-hl7-input",
                "source_port": 2580,
                "pre_queue": None,
                "post_queue": None,
                "subscriptions": [],
            },
            "bcu-to-chemo": {
                "topic": "prefix-sbt-mpi-hl7-input",
                "source_port": None,
                "pre_queue": None,
                "post_queue": None,
                "subscriptions": [
                    {
                        "name": "prefix-sbs-bcu-chemo",
                        "topic": "prefix-sbt-mpi-hl7-input",
                        "consumer_apps": [{"app_name": "bcu-sender", "microservice_id": "bcu_sender", "workflow_id": "bcu-to-chemo"}],
                    }
                ],
            },
        }

        _merge_subscription_sender_flows(flows)

        assert "bcu-to-chemo" not in flows
        assert flows["mpi-to-topic"]["subscriptions"][0]["consumer_apps"][0]["app_name"] == "bcu-sender"

    def test_unknown_flow_gets_generated_metadata(self) -> None:
        apps: list[dict[str, Any]] = [
            {
                "name": "new-server-ca",
                "env": {
                    "WORKFLOW_ID": "new-system-to-mpi",
                    "EGRESS_QUEUE_NAME": "prefix-sbq-new-transformer",
                },
                "target_port": 9999,
            },
        ]
        flow = _build_flow("new-system-to-mpi", apps)

        assert flow["label"] == "New System To Mpi"
        assert flow["source"] == "NEW"
        assert flow["icon"] == "bi-arrow-left-right"
