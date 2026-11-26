from __future__ import annotations

from unittest.mock import patch

from dashboard.services.service_bus import get_namespace_snapshot


def test_namespace_snapshot_keeps_all_subscription_consumers() -> None:
    topic = {
        "name": "topic-a",
        "status": "Active",
        "active_message_count": 0,
        "dead_letter_message_count": 0,
        "scheduled_message_count": 0,
        "subscription_count": 1,
        "size_in_bytes": 0,
        "max_size_in_megabytes": 0,
    }
    consumers = {
        "topic-a": [
            {
                "name": "sub-a",
                "entity_name": "topic-a/sub-a",
                "consumer_apps": [
                    {
                        "app_name": "sender-one",
                        "microservice_id": "sender_one",
                        "workflow_id": "mpi-to-topic",
                    }
                ],
            },
            {
                "name": "sub-a",
                "entity_name": "topic-a/sub-a",
                "consumer_apps": [
                    {
                        "app_name": "sender-two",
                        "microservice_id": "sender_two",
                        "workflow_id": "mpi-to-topic",
                    }
                ],
            },
        ]
    }

    with (
        patch("dashboard.services.service_bus.get_queues", return_value=[]),
        patch("dashboard.services.service_bus.get_topics", return_value=[topic]),
        patch("dashboard.services.service_bus.get_subscriptions", return_value=[]),
        patch("dashboard.services.arm.get_subscription_consumers_by_topic", return_value=consumers),
    ):
        snapshot = get_namespace_snapshot()

    subscription = snapshot["topics"][0]["subscriptions"][0]
    assert [app["app_name"] for app in subscription["consumer_apps"]] == ["sender-one", "sender-two"]


def test_namespace_snapshot_fetches_topic_subscriptions_in_parallel() -> None:
    import threading  # noqa: PLC0415

    topics = [
        {
            "name": f"topic-{i}",
            "status": "Active",
            "active_message_count": 0,
            "dead_letter_message_count": 0,
            "scheduled_message_count": 0,
            "subscription_count": 1,
            "size_in_bytes": 0,
            "max_size_in_megabytes": 0,
        }
        for i in range(3)
    ]
    barrier = threading.Barrier(3, timeout=2.0)

    def _parallel_get_subs(topic_name: str) -> list[dict]:
        barrier.wait()
        return [
            {
                "name": f"sub-{topic_name}",
                "status": "Active",
                "active_message_count": 1,
                "dead_letter_message_count": 0,
                "message_count": 1,
            }
        ]

    with (
        patch("dashboard.services.service_bus.get_queues", return_value=[]),
        patch("dashboard.services.service_bus.get_topics", return_value=topics),
        patch("dashboard.services.service_bus.get_subscriptions", side_effect=_parallel_get_subs),
        patch("dashboard.services.arm.get_subscription_consumers_by_topic", return_value={}),
    ):
        snapshot = get_namespace_snapshot()

    assert [t["name"] for t in snapshot["topics"]] == ["topic-0", "topic-1", "topic-2"]
    assert snapshot["kpis"]["subscription_count"] == 3
    assert snapshot["kpis"]["subscription_active_messages"] == 3


def test_get_client_reuses_singleton_per_subscription() -> None:
    from dashboard.services import service_bus  # noqa: PLC0415

    with (
        patch.object(service_bus.config, "AZURE_SUBSCRIPTION_ID", "sub-a"),
        patch("dashboard.services.service_bus.get_azure_credential", return_value=object()),
        patch("dashboard.services.service_bus.ServiceBusManagementClient") as mock_cls,
    ):
        c1 = service_bus._get_client()
        c2 = service_bus._get_client()

    assert c1 is c2
    mock_cls.assert_called_once()


def test_get_message_metrics_uses_shared_logs_client_without_tolower() -> None:
    from types import SimpleNamespace  # noqa: PLC0415
    from unittest.mock import MagicMock  # noqa: PLC0415

    from azure.monitor.query import LogsQueryStatus  # noqa: PLC0415

    from dashboard.services import service_bus  # noqa: PLC0415

    mock_client = MagicMock()
    mock_client.query_workspace.return_value = SimpleNamespace(
        status=LogsQueryStatus.SUCCESS,
        tables=[SimpleNamespace(rows=[])],
    )

    with (
        patch.object(service_bus.config, "AZURE_LOG_ANALYTICS_WORKSPACE_ID", "ws-1"),
        patch.object(service_bus.config, "AZURE_SERVICE_BUS_NAMESPACE", "sbns-dev"),
        patch("dashboard.services.service_bus._get_logs_client", return_value=mock_client),
    ):
        service_bus.get_message_metrics(timespan_hours=24, entity_type="queue", entity_name="pre-phw-transform")

    query = mock_client.query_workspace.call_args.kwargs["query"]
    assert "tolower(" not in query
    assert "Resource =~ 'sbns-dev'" in query
    assert "ResourceId contains '/queues/pre-phw-transform'" in query


def test_demo_mode_namespace_snapshot_includes_topics_subscriptions_and_consumers() -> None:
    from dashboard.services import service_bus  # noqa: PLC0415

    with patch.object(service_bus.config, "DEMO_MODE", True):
        snapshot = get_namespace_snapshot()

    assert len(snapshot["queues"]) > 0
    assert len(snapshot["topics"]) >= 2
    mpi_topic = next(t for t in snapshot["topics"] if t["name"] == "demo-sbt-mpi-hl7-input")
    sub_names = [s["name"] for s in mpi_topic["subscriptions"]]
    assert sub_names == ["downstream-a", "downstream-b", "downstream-c"]
    sub_a = next(s for s in mpi_topic["subscriptions"] if s["name"] == "downstream-a")
    assert len(sub_a["consumer_apps"]) == 1
    assert snapshot["kpis"]["subscription_count"] == 5
