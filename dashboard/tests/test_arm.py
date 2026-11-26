"""
Unit tests for Container App discovery (arm.py).
Tests the classification and flow-building logic — no Azure calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from dashboard.services import arm
from dashboard.services.arm import (
    _build_flow,
    _classify_app,
    _merge_subscription_sender_flows,
    parse_flow_tag,
    resolve_flow_ids,
)


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

    def test_subscription_transformer(self) -> None:
        env = {
            "INGRESS_TOPIC_NAME": "some-topic",
            "INGRESS_SUBSCRIPTION_NAME": "some-sub",
            "EGRESS_QUEUE_NAME": "post-q",
            "WORKFLOW_ID": "wds-to-wis",
        }
        assert _classify_app(env) == "subscription_transformer"

    def test_subscription_transformer_with_egress_topic(self) -> None:
        env = {
            "INGRESS_TOPIC_NAME": "prefix-sbt-phw-hl7-input",
            "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-phw-tfmr",
            "EGRESS_TOPIC_NAME": "prefix-sbt-phw-hl7-output",
            "WORKFLOW_ID": "phw-to-mpi",
        }
        assert _classify_app(env) == "subscription_transformer"

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

    def test_topic_subscription_transformer_flow(self) -> None:
        apps: list[dict[str, Any]] = [
            {
                "name": "wds-hl7transformer-ca",
                "env": {
                    "WORKFLOW_ID": "wds-to-wis",
                    "INGRESS_TOPIC_NAME": "prefix-sbt-wds-hl7-input",
                    "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-wds-wis-transformer",
                    "EGRESS_QUEUE_NAME": "prefix-sbq-wis-soap-sender",
                    "MICROSERVICE_ID": "wds_hl7_transformer",
                },
                "target_port": None,
            },
            {
                "name": "wis-soap-sender-ca",
                "env": {
                    "WORKFLOW_ID": "wds-to-wis",
                    "INGRESS_QUEUE_NAME": "prefix-sbq-wis-soap-sender",
                    "MICROSERVICE_ID": "wis_soap_sender",
                },
                "target_port": None,
            },
        ]
        flow = _build_flow("wds-to-wis", apps)

        assert flow["label"] == "WDS → WIS"
        assert flow["topic"] == "prefix-sbt-wds-hl7-input"
        assert flow["post_topic"] is None
        assert flow["post_queue"] == "prefix-sbq-wis-soap-sender"
        assert flow["transformer"] == "WDS Transformer"
        assert flow["subscriptions"][0]["name"] == "prefix-sbs-wds-wis-transformer"
        assert flow["subscriptions"][0]["consumer_apps"][0]["sender_type"] == "subscription_transformer"

    def test_topic_to_topic_transformer_flow(self) -> None:
        apps: list[dict[str, Any]] = [
            {
                "name": "phw-hl7server-ca",
                "env": {
                    "WORKFLOW_ID": "phw-to-mpi",
                    "EGRESS_TOPIC_NAME": "prefix-sbt-phw-hl7-input",
                    "MICROSERVICE_ID": "phw-hl7server-ca",
                },
                "target_port": 2575,
            },
            {
                "name": "phw-hl7transformer-ca",
                "env": {
                    "WORKFLOW_ID": "phw-to-mpi",
                    "INGRESS_TOPIC_NAME": "prefix-sbt-phw-hl7-input",
                    "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-phw-tfmr",
                    "EGRESS_TOPIC_NAME": "prefix-sbt-phw-hl7-output",
                    "MICROSERVICE_ID": "phw-hl7transformer-ca",
                },
                "target_port": None,
            },
            {
                "name": "phw-to-mpi-hl7sender-ca",
                "env": {
                    "WORKFLOW_ID": "phw-to-mpi",
                    "INGRESS_TOPIC_NAME": "prefix-sbt-phw-hl7-output",
                    "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-phw-mpi-sndr",
                    "RECEIVER_MLLP_HOST": "mpi.example",
                    "RECEIVER_MLLP_PORT": "2576",
                    "MICROSERVICE_ID": "phw-to-mpi-hl7sender-ca",
                },
                "target_port": None,
            },
        ]
        flow = _build_flow("phw-to-mpi", apps)

        assert flow["label"] == "PHW → MPI"
        assert flow["source_port"] == 2575
        assert flow["topic"] == "prefix-sbt-phw-hl7-input"
        assert flow["post_topic"] == "prefix-sbt-phw-hl7-output"
        assert flow["post_queue"] is None
        assert flow["transformer"] == "PHW Transformer"
        assert (flow["destination_host"], flow["destination_port"]) == ("mpi.example", 2576)
        assert [(s["topic"], s["name"]) for s in flow["subscriptions"]] == [
            ("prefix-sbt-phw-hl7-input", "prefix-sbs-phw-tfmr"),
            ("prefix-sbt-phw-hl7-output", "prefix-sbs-phw-mpi-sndr"),
        ]
        assert flow["subscriptions"][0]["consumer_apps"][0]["sender_type"] == "subscription_transformer"
        assert flow["subscriptions"][1]["consumer_apps"][0]["sender_type"] == "subscription_sender"

    def test_wpas_to_proms_and_cav_pms_to_wrrs_use_display_metadata(self) -> None:
        wpas_flow = _build_flow(
            "wpas-to-proms",
            [
                {
                    "name": "uks-dev-wpas-restserver-ca",
                    "env": {"WORKFLOW_ID": "wpas-to-proms", "EGRESS_TOPIC_NAME": "sbt-wpas-ingress"},
                    "target_port": 3584,
                },
                {
                    "name": "uks-dev-proms-fhir-tfmr-ca",
                    "env": {
                        "WORKFLOW_ID": "wpas-to-proms",
                        "INGRESS_TOPIC_NAME": "sbt-wpas-ingress",
                        "INGRESS_SUBSCRIPTION_NAME": "sbs-wpas-proms-tfmr",
                        "EGRESS_QUEUE_NAME": "sbq-proms-fhir-egress",
                    },
                    "target_port": None,
                },
            ],
        )
        assert wpas_flow["label"] == "WPAS → PROMS"
        assert wpas_flow["source"] == "WPAS"
        assert wpas_flow["destination"] == "PROMS"
        assert wpas_flow["transformer"] == "PROMS FHIR Transformer"

        pms_wrrs_flow = _build_flow(
            "cav-pms-to-wrrs",
            [
                {
                    "name": "uks-dev-pms-wrrs-idupd-ca",
                    "env": {
                        "WORKFLOW_ID": "cav-pms-to-wrrs",
                        "INGRESS_TOPIC_NAME": "sbt-pms-hl7-input",
                        "INGRESS_SUBSCRIPTION_NAME": "sbs-pms-wrrs-sender",
                    },
                    "target_port": None,
                },
            ],
        )
        assert pms_wrrs_flow["label"] == "CAV PMS → WRRS"
        assert pms_wrrs_flow["source"] == "PMS"
        assert pms_wrrs_flow["destination"] == "WRRS"

    def test_merge_does_not_absorb_topic_to_topic_transformer_flow(self) -> None:
        flows: dict[str, dict[str, Any]] = {
            "owner": {
                "topic": "sbt-shared-input",
                "source_port": 2582,
                "pre_queue": None,
                "post_queue": None,
                "post_topic": None,
                "subscriptions": [],
            },
            "downstream-tfmr": {
                "topic": "sbt-shared-input",
                "source_port": None,
                "pre_queue": None,
                "post_queue": None,
                "post_topic": "sbt-downstream-output",
                "subscriptions": [{"name": "sbs-tfmr", "topic": "sbt-shared-input", "consumer_apps": []}],
            },
        }
        _merge_subscription_sender_flows(flows)
        assert "downstream-tfmr" in flows

    def test_merge_subscription_sender_flow_keeps_consumer_metadata(self) -> None:
        flows: dict[str, dict[str, Any]] = {
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
                        "consumer_apps": [
                            {
                                "app_name": "bcu-sender",
                                "microservice_id": "bcu_sender",
                                "workflow_id": "bcu-to-chemo",
                            }
                        ],
                    }
                ],
            },
        }

        _merge_subscription_sender_flows(flows)

        assert "bcu-to-chemo" not in flows
        assert flows["mpi-to-topic"]["subscriptions"][0]["consumer_apps"][0]["app_name"] == "bcu-sender"

    def test_wds_to_wis_flow_uses_explicit_display_metadata(self) -> None:
        apps: list[dict[str, Any]] = [
            {
                "name": "wds-hl7-transformer-ca",
                "env": {
                    "WORKFLOW_ID": "wds-to-wis",
                    "INGRESS_QUEUE_NAME": "local-inthub-wds-transformer-ingress",
                    "EGRESS_QUEUE_NAME": "local-inthub-wis-soap-sender-ingress",
                    "MICROSERVICE_ID": "wds_hl7_transformer",
                },
                "target_port": None,
            },
            {
                "name": "wis-soap-sender-ca",
                "env": {
                    "WORKFLOW_ID": "wds-to-wis",
                    "INGRESS_QUEUE_NAME": "local-inthub-wis-soap-sender-ingress",
                    "MICROSERVICE_ID": "wis_soap_sender",
                },
                "target_port": None,
            },
        ]

        flow = _build_flow("wds-to-wis", apps)

        assert flow["label"] == "WDS → WIS"
        assert flow["source"] == "WDS"
        assert flow["destination"] == "WIS"
        assert flow["pre_queue"] == "local-inthub-wds-transformer-ingress"
        assert flow["post_queue"] == "local-inthub-wis-soap-sender-ingress"
        assert flow["transformer"] == "WDS Transformer"

    def test_lims_to_hub_flow_uses_explicit_display_metadata(self) -> None:
        apps: list[dict[str, Any]] = [
            {
                "name": "lims-restserver-ca",
                "env": {
                    "WORKFLOW_ID": "lims-to-hub",
                    "EGRESS_TOPIC_NAME": "local-inthub-lims-hl7-input",
                    "MICROSERVICE_ID": "lims_rest_server",
                },
                "target_port": 10802,
            },
            {
                "name": "lims-mpi-sender-ca",
                "env": {
                    "WORKFLOW_ID": "lims-to-hub",
                    "INGRESS_TOPIC_NAME": "local-inthub-lims-hl7-input",
                    "INGRESS_SUBSCRIPTION_NAME": "local-inthub-lims-mpi-sender",
                    "MICROSERVICE_ID": "hl7_lims_mpi_sender",
                },
                "target_port": None,
            },
            {
                "name": "lims-trrr-sender-ca",
                "env": {
                    "WORKFLOW_ID": "lims-to-hub",
                    "INGRESS_TOPIC_NAME": "local-inthub-lims-hl7-input",
                    "INGRESS_SUBSCRIPTION_NAME": "local-inthub-lims-trrr-sender",
                    "MICROSERVICE_ID": "hl7_lims_trrr_sender",
                },
                "target_port": None,
            },
        ]

        flow = _build_flow("lims-to-hub", apps)

        assert flow["label"] == "LIMS → Hub"
        assert flow["source"] == "LIMS"
        assert flow["destination"] == "MPI / TRRR"
        assert flow["transformer"] is None
        assert flow["source_port"] == 10802
        assert flow["topic"] == "local-inthub-lims-hl7-input"
        assert {sub["name"] for sub in flow["subscriptions"]} == {
            "local-inthub-lims-mpi-sender",
            "local-inthub-lims-trrr-sender",
        }

    def test_lims_topic_owner_is_recognised_for_flow_merge(self) -> None:
        flows: dict[str, dict[str, Any]] = {
            "lims-to-hub": {
                "topic": "local-inthub-lims-hl7-input",
                "source_port": 10802,
                "pre_queue": None,
                "post_queue": None,
                "subscriptions": [],
            },
            "lims-trrr-sender": {
                "topic": "local-inthub-lims-hl7-input",
                "source_port": None,
                "pre_queue": None,
                "post_queue": None,
                "subscriptions": [
                    {
                        "name": "local-inthub-lims-trrr-sender",
                        "topic": "local-inthub-lims-hl7-input",
                        "consumer_apps": [
                            {
                                "app_name": "lims-trrr-sender-ca",
                                "microservice_id": "hl7_lims_trrr_sender",
                                "workflow_id": "lims-to-hub",
                            }
                        ],
                    }
                ],
            },
        }

        _merge_subscription_sender_flows(flows)

        assert "lims-trrr-sender" not in flows
        assert flows["lims-to-hub"]["subscriptions"][0]["name"] == "local-inthub-lims-trrr-sender"

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


class TestFlowTag:
    def test_parse_trims_lowercases_dedupes_and_drops_invalid_entries(self) -> None:
        tag = " WDS-to-WIS, wds-to-mpi ,wds-to-wis,, bad id,<x>"
        assert parse_flow_tag(tag) == ["wds-to-wis", "wds-to-mpi"]

    def test_missing_tag_uses_workflow_id(self) -> None:
        assert resolve_flow_ids([], "phw-to-mpi", {"phw-to-mpi"}) == ["phw-to-mpi"]

    def test_tag_need_not_list_own_workflow_id(self) -> None:
        # The MPI server's WORKFLOW_ID (mpi-to-topic) is its telemetry identity, not a flow.
        known = {"mpi-to-topic", "sww-to-chemo", "mpi-to-phw"}
        assert resolve_flow_ids(["sww-to-chemo", "mpi-to-phw"], "mpi-to-topic", known) == ["sww-to-chemo", "mpi-to-phw"]

    def test_entries_without_a_matching_workflow_id_are_ignored(self) -> None:
        # e.g. the old "mpi-outbound" tag must not invent a flow that no telemetry or alarm rule uses.
        assert resolve_flow_ids(["mpi-outbound"], "sww-to-chemo", {"sww-to-chemo"}) == ["sww-to-chemo"]


def _app(name: str, env: dict[str, str], target_port: int | None = None, tag: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "env": env,
        "target_port": target_port,
        "fqdn": None,
        "flow_tag": parse_flow_tag(tag),
    }


def _discover(apps: list[dict[str, Any]]) -> dict[str, dict]:
    with (
        patch.object(arm, "_is_configured", return_value=True),
        patch.object(arm, "_list_container_apps", return_value=apps),
        # discover_flows rebinds the module caches; restore them so other tests are unaffected.
        patch.object(arm, "_cached_flows", {}),
        patch.object(arm, "_cached_apps", []),
        patch.object(arm, "_cache_timestamp", 0.0),
    ):
        return arm.discover_flows(force=True)


def _wds_apps(server_tag: str | None) -> list[dict[str, Any]]:
    topic = "prefix-sbt-wds-hl7-input"
    return [
        _app(
            "wds-hl7server-ca",
            {"WORKFLOW_ID": "wds-to-mpi", "EGRESS_TOPIC_NAME": topic},
            target_port=2582,
            tag=server_tag,
        ),
        _app(
            "wds-mpi-sender-ca",
            {
                "WORKFLOW_ID": "wds-to-mpi",
                "INGRESS_TOPIC_NAME": topic,
                "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-wds-mpi-sender",
                "RECEIVER_MLLP_HOST": "mpi.example",
                "RECEIVER_MLLP_PORT": "2576",
            },
            tag="wds-to-mpi",
        ),
        _app(
            "wds-hl7transformer-ca",
            {
                "WORKFLOW_ID": "wds-to-wis",
                "INGRESS_TOPIC_NAME": topic,
                "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-wds-wis-transformer",
                "EGRESS_QUEUE_NAME": "prefix-sbq-wis-soap-sender",
            },
            tag="wds-to-wis",
        ),
        _app(
            "wds-phw-sender-ca",
            {
                "WORKFLOW_ID": "wds-to-phw",
                "INGRESS_TOPIC_NAME": topic,
                "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-wds-phw-sender",
                "RECEIVER_MLLP_HOST": "phw.example",
                "RECEIVER_MLLP_PORT": "2590",
            },
            tag="wds-to-phw",
        ),
    ]


class TestDiscoverFlowsWithFlowTag:
    def test_list_container_apps_reads_flow_tag_case_insensitively(self) -> None:
        container = SimpleNamespace(env=[SimpleNamespace(name="WORKFLOW_ID", value="wds-to-mpi")])
        app = SimpleNamespace(
            name="wds-hl7server-ca",
            tags={"Integration-Hub-Flow": "wds-to-mpi,wds-to-wis"},
            template=SimpleNamespace(containers=[container]),
            configuration=None,
        )
        client = SimpleNamespace(container_apps=SimpleNamespace(list_by_resource_group=lambda _rg: [app]))

        with (
            patch.object(arm, "get_azure_credential"),
            patch.object(arm, "ContainerAppsAPIClient", return_value=client),
        ):
            apps = arm._list_container_apps()

        assert apps[0]["flow_tag"] == ["wds-to-mpi", "wds-to-wis"]

    def test_shared_server_joins_every_tagged_flow(self) -> None:
        flows = _discover(_wds_apps("wds-to-mpi,wds-to-wis,wds-to-phw"))

        assert set(flows) == {"wds-to-mpi", "wds-to-wis", "wds-to-phw"}
        for flow in flows.values():
            assert flow["source_port"] == 2582
            assert flow["topic"] == "prefix-sbt-wds-hl7-input"
        # Each flow lists only its own subscription on the shared topic.
        assert [s["name"] for s in flows["wds-to-mpi"]["subscriptions"]] == ["prefix-sbs-wds-mpi-sender"]
        assert [s["name"] for s in flows["wds-to-wis"]["subscriptions"]] == ["prefix-sbs-wds-wis-transformer"]
        assert [s["name"] for s in flows["wds-to-phw"]["subscriptions"]] == ["prefix-sbs-wds-phw-sender"]
        assert flows["wds-to-wis"]["post_queue"] == "prefix-sbq-wis-soap-sender"
        assert (flows["wds-to-mpi"]["destination_host"], flows["wds-to-mpi"]["destination_port"]) == (
            "mpi.example",
            2576,
        )
        assert (flows["wds-to-phw"]["destination_host"], flows["wds-to-phw"]["destination_port"]) == (
            "phw.example",
            2590,
        )

    def test_untagged_server_keeps_merging_consumer_only_flows(self) -> None:
        flows = _discover(_wds_apps(None))

        # wds-to-phw has only a subscription sender, so it is folded into the topic owner as before.
        assert set(flows) == {"wds-to-mpi", "wds-to-wis"}
        assert flows["wds-to-wis"]["source_port"] is None
        assert {s["name"] for s in flows["wds-to-mpi"]["subscriptions"]} == {
            "prefix-sbs-wds-mpi-sender",
            "prefix-sbs-wds-phw-sender",
        }

    def test_server_publishing_to_two_topics_uses_the_topic_its_flow_consumes(self) -> None:
        server = _app(
            "risp-restserver-ca",
            {
                "WORKFLOW_ID": "risp-to-mpi",
                "EGRESS_TOPIC_NAME": "prefix-sbt-risp-hl7-input",
                "WRRS_TOPIC_NAME": "prefix-sbt-risp-wrrs-outbound",
            },
            target_port=2586,
            tag="risp-to-mpi,risp-to-wrrs",
        )
        wrrs_sender = _app(
            "wrrs-stmsg-dbsender-ca",
            {
                "WORKFLOW_ID": "risp-to-wrrs",
                "INGRESS_TOPIC_NAME": "prefix-sbt-risp-wrrs-outbound",
                "INGRESS_SUBSCRIPTION_NAME": "prefix-sbs-risp-wrrs-sender",
            },
            tag="risp-to-wrrs",
        )

        flows = _discover([server, wrrs_sender])

        assert flows["risp-to-mpi"]["topic"] == "prefix-sbt-risp-hl7-input"
        assert flows["risp-to-wrrs"]["topic"] == "prefix-sbt-risp-wrrs-outbound"
        assert flows["risp-to-wrrs"]["source_port"] == 2586

    def test_server_tagged_only_with_downstream_flows_has_no_flow_of_its_own(self) -> None:
        topic = "prefix-sbt-mpi-hl7-input"
        apps = [
            _app(
                "mpi-hl7server-ca",
                {"WORKFLOW_ID": "mpi-to-topic", "EGRESS_TOPIC_NAME": topic},
                target_port=2580,
                tag="sww-to-chemo,mpi-to-phw",
            ),
            _app(
                "sww-chemo-sender-ca",
                {"WORKFLOW_ID": "sww-to-chemo", "INGRESS_TOPIC_NAME": topic, "INGRESS_SUBSCRIPTION_NAME": "sbs-sww"},
                tag="sww-to-chemo",
            ),
            _app(
                "mpi-phw-sender-ca",
                # Stale pre-change tag value: ignored because no app has WORKFLOW_ID "mpi-outbound".
                {"WORKFLOW_ID": "mpi-to-phw", "INGRESS_TOPIC_NAME": topic, "INGRESS_SUBSCRIPTION_NAME": "sbs-phw"},
                tag="mpi-outbound",
            ),
        ]

        flows = _discover(apps)

        assert set(flows) == {"sww-to-chemo", "mpi-to-phw"}
        assert flows["sww-to-chemo"]["source_port"] == 2580
        assert [s["name"] for s in flows["mpi-to-phw"]["subscriptions"]] == ["sbs-phw"]
