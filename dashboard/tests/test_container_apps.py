from __future__ import annotations

from unittest.mock import patch

from dashboard.services.container_apps import _build_app_flow_map


class TestBuildAppFlowMap:
    def test_uses_discovered_workflow_id_when_flow_exists(self) -> None:
        cached_apps = [
            {
                "name": "phw-transformer-ca",
                "env": {
                    "WORKFLOW_ID": "phw-to-mpi",
                },
            }
        ]
        flows = {"phw-to-mpi": {"topic": None, "source_port": 2575}}

        with (
            patch("dashboard.services.container_apps.arm.discover_flows", return_value=flows),
            patch("dashboard.services.container_apps.arm._cached_apps", cached_apps),
        ):
            assert _build_app_flow_map() == {"phw-transformer-ca": "phw-to-mpi"}

    def test_maps_removed_subscription_sender_workflow_to_topic_owner(self) -> None:
        cached_apps = [
            {
                "name": "bcu-subscription-sender-ca",
                "env": {
                    "WORKFLOW_ID": "bcu-to-chemo",
                    "INGRESS_TOPIC_NAME": "prefix-sbt-mpi-hl7-input",
                    "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-bcu-chemo",
                },
            }
        ]
        flows = {
            "mpi-to-topic": {
                "topic": "prefix-sbt-mpi-hl7-input",
                "source_port": 2580,
            }
        }

        with (
            patch("dashboard.services.container_apps.arm.discover_flows", return_value=flows),
            patch("dashboard.services.container_apps.arm._cached_apps", cached_apps),
        ):
            assert _build_app_flow_map() == {"bcu-subscription-sender-ca": "mpi-to-topic"}
