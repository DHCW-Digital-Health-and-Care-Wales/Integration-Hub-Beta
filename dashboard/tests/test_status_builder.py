from __future__ import annotations

from unittest.mock import patch

from dashboard.services.status_builder import build_status


def test_subscription_dlq_affects_namespace_kpis() -> None:
    namespace_snapshot = {
        "queues": [],
        "topics": [
            {
                "name": "topic-a",
                "active_message_count": 0,
                "dead_letter_message_count": 0,
                "subscriptions": [
                    {
                        "name": "sub-a",
                        "active_message_count": 3,
                        "dead_letter_message_count": 2,
                    }
                ],
            }
        ],
        "kpis": {
            "queue_active_messages": 0,
            "queue_dead_letter_messages": 0,
            "topic_active_messages": 0,
            "topic_dead_letter_messages": 0,
            "subscription_active_messages": 3,
            "subscription_dead_letter_messages": 2,
            "queue_count": 0,
            "topic_count": 1,
            "subscription_count": 1,
        },
    }

    with (
        patch("dashboard.services.status_builder.get_namespace_snapshot", return_value=namespace_snapshot),
        patch("dashboard.services.status_builder.get_active_flows", return_value={}),
        patch("dashboard.services.status_builder.get_exceptions", return_value=[]),
        patch("dashboard.services.status_builder.get_retry_delay_metrics_by_flow", return_value=[]),
    ):
        status = build_status()

    assert status["namespace_kpis"]["subscription_dead_letter_messages"] == 2
    assert status["kpis"]["total_dlq_messages"] == 2