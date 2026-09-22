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
