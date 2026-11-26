"""
Demo / simulation data for DEMO_MODE=true.

Set DEMO_MODE=true in your environment (or .env) to run the dashboard
entirely on synthetic data — no Azure credentials required.  Useful for
layout testing, stakeholder demos, and stress-testing the UI with many
flows in varied health states.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=timezone.utc)


def _ts(minutes_ago: int = 0) -> str:
    return (_NOW - timedelta(minutes=minutes_ago)).isoformat()


def _queue(name: str, active: int = 0, dlq: int = 0) -> dict:
    return {
        "name": name,
        "status": "Active",
        "active_message_count": active,
        "dead_letter_message_count": dlq,
        "scheduled_message_count": 0,
        "message_count": active + dlq,
        "size_in_bytes": active * 2048,
        "max_size_in_megabytes": 1024,
    }


# ---------------------------------------------------------------------------
# Flows  (same shape as flows.FLOWS)
# ---------------------------------------------------------------------------

DEMO_FLOWS: dict[str, dict] = {
    "phw-to-mpi": {
        "label": "PHW → MPI",
        "source": "PHW",
        "source_port": 2575,
        "pre_queue": "demo-sbq-phw-hl7-transformer",
        "transformer": "PHW Transformer",
        "post_queue": "demo-sbq-phw-hl7-sender",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#3b82f6",
        "icon": "bi-heart-pulse",
    },
    "paris-to-mpi": {
        "label": "Paris → MPI",
        "source": "Paris",
        "source_port": 2577,
        "pre_queue": "demo-sbq-paris-pre",
        "transformer": None,
        "post_queue": "demo-sbq-paris-post",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#a855f7",
        "icon": "bi-activity",
    },
    "mosaiq-to-mpi": {
        "label": "Mosaiq → MPI",
        "source": "Mosaiq",
        "source_port": 2583,
        "pre_queue": "demo-sbq-mosaiq-pre",
        "transformer": None,
        "post_queue": "demo-sbq-mosaiq-post",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#ec4899",
        "icon": "bi-radioactive",
    },
    "chemocare-to-mpi": {
        "label": "ChemoCare → MPI",
        "source": "ChemoCare",
        "source_port": 2578,
        "pre_queue": "demo-sbq-chemo-hl7-transformer",
        "transformer": "Chemo Transformer",
        "post_queue": "demo-sbq-chemo-hl7-sender",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#06b6d4",
        "icon": "bi-capsule",
    },
    "pims-to-mpi": {
        "label": "PIMS → MPI",
        "source": "PIMS",
        "source_port": 2579,
        "pre_queue": "demo-sbq-pims-hl7-transformer",
        "transformer": "PIMS Transformer",
        "post_queue": "demo-sbq-pims-hl7-sender",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#22c55e",
        "icon": "bi-clipboard2-pulse",
    },
    "wds-to-mpi": {
        "label": "WDS → MPI",
        "source": "WDS",
        "source_port": 2582,
        "pre_queue": "demo-sbq-wds-hl7-transformer",
        "transformer": None,
        "post_queue": "demo-sbq-wds-hl7-sender",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#f97316",
        "icon": "bi-hospital",
    },
    "mpi-outbound": {
        "label": "MPI Outbound",
        "source": "MPI",
        "source_port": 2580,
        "pre_queue": None,
        "transformer": None,
        "post_queue": None,
        "topic": "demo-sbt-mpi-hl7-input",
        "subscriptions": [
            {"name": "downstream-a", "active_message_count": 0, "dead_letter_message_count": 0},
            {"name": "downstream-b", "active_message_count": 3, "dead_letter_message_count": 0},
            {"name": "downstream-c", "active_message_count": 72, "dead_letter_message_count": 2},
        ],
        "destination": "Downstream Systems",
        "colour": "#f59e0b",
        "icon": "bi-broadcast",
    },
    # --- Additional fictional flows to stress-test the UI ---
    "werfen-to-mpi": {
        "label": "Werfen → MPI",
        "source": "Werfen",
        "source_port": 2583,
        "pre_queue": "demo-sbq-werfen-pre",
        "transformer": "Werfen Transformer",
        "post_queue": "demo-sbq-werfen-post",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#ec4899",
        "icon": "bi-droplet-fill",
    },
    "radiology-to-mpi": {
        "label": "Radiology → MPI",
        "source": "Radiology",
        "source_port": 2584,
        "pre_queue": "demo-sbq-radiology-pre",
        "transformer": "Radiology Transformer",
        "post_queue": "demo-sbq-radiology-post",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#8b5cf6",
        "icon": "bi-radioactive",
    },
    "theatres-to-mpi": {
        "label": "Theatres → MPI",
        "source": "Theatres",
        "source_port": 2585,
        "pre_queue": "demo-sbq-theatres-pre",
        "transformer": None,
        "post_queue": "demo-sbq-theatres-post",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#14b8a6",
        "icon": "bi-scissors",
    },
    "pharmacy-to-mpi": {
        "label": "Pharmacy → MPI",
        "source": "Pharmacy",
        "source_port": 2586,
        "pre_queue": "demo-sbq-pharmacy-pre",
        "transformer": "Pharmacy Transformer",
        "post_queue": "demo-sbq-pharmacy-post",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#f43f5e",
        "icon": "bi-capsule-pill",
    },
    "maternity-to-mpi": {
        "label": "Maternity → MPI",
        "source": "Maternity",
        "source_port": 2587,
        "pre_queue": "demo-sbq-maternity-pre",
        "transformer": None,
        "post_queue": "demo-sbq-maternity-post",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#fb7185",
        "icon": "bi-person-heart",
    },
    "pathology-to-mpi": {
        "label": "Pathology → MPI",
        "source": "Pathology",
        "source_port": 2588,
        "pre_queue": "demo-sbq-pathology-pre",
        "transformer": "Pathology Transformer",
        "post_queue": "demo-sbq-pathology-post",
        "topic": None,
        "subscriptions": [],
        "destination": "MPI",
        "colour": "#a3e635",
        "icon": "bi-flask",
    },
}

# Synthesise reachable-looking source/destination host:port pairs for every demo
# flow so the network connectivity test page has data to show without needing
# real Container App discovery.
for _flow_id, _flow in DEMO_FLOWS.items():
    _flow.setdefault("source_host", f"demo-{_flow_id}.internal.example.com" if _flow.get("source_port") else None)
    _flow.setdefault("destination_host", "demo-mpi.internal.example.com" if _flow.get("destination") else None)
    _flow.setdefault("destination_port", 16005 if _flow.get("destination") else None)
del _flow_id, _flow


# ---------------------------------------------------------------------------
# Queues  (same shape as service_bus.get_queues())
# ---------------------------------------------------------------------------
#
# Health thresholds (defaults): warning ≥ 10, critical ≥ 50, dlq ≥ 1
# The counts below deliberately produce a mix of states.
# ---------------------------------------------------------------------------

DEMO_QUEUES: list[dict] = [
    # PHW — healthy
    _queue("demo-sbq-phw-hl7-transformer", active=2),
    _queue("demo-sbq-phw-hl7-sender", active=0),
    # Paris — warning (active ≥ 10)
    _queue("demo-sbq-paris-pre", active=14),
    _queue("demo-sbq-paris-post", active=1),
    # ChemoCare — critical (active ≥ 50)
    _queue("demo-sbq-chemo-hl7-transformer", active=63),
    _queue("demo-sbq-chemo-hl7-sender", active=5),
    # PIMS — warning (DLQ hit)
    _queue("demo-sbq-pims-hl7-transformer", active=4, dlq=3),
    _queue("demo-sbq-pims-hl7-sender", active=0),
    # WDS — healthy
    _queue("demo-sbq-wds-hl7-transformer", active=0),
    _queue("demo-sbq-wds-hl7-sender", active=1),
    # Werfen — critical (DLQ backlog)
    _queue("demo-sbq-werfen-pre", active=7, dlq=12),
    _queue("demo-sbq-werfen-post", active=0),
    # Radiology — healthy
    _queue("demo-sbq-radiology-pre", active=3),
    _queue("demo-sbq-radiology-post", active=1),
    # Theatres — warning
    _queue("demo-sbq-theatres-pre", active=18),
    _queue("demo-sbq-theatres-post", active=6),
    # Pharmacy — healthy
    _queue("demo-sbq-pharmacy-pre", active=0),
    _queue("demo-sbq-pharmacy-post", active=0),
    # Maternity — critical
    _queue("demo-sbq-maternity-pre", active=87),
    _queue("demo-sbq-maternity-post", active=22),
    # Pathology — healthy
    _queue("demo-sbq-pathology-pre", active=1),
    _queue("demo-sbq-pathology-post", active=0),
]


# ---------------------------------------------------------------------------
# Exceptions  (same shape as azure_monitor.get_exceptions())
# ---------------------------------------------------------------------------

DEMO_EXCEPTIONS: list[dict] = [
    {
        "timestamp": _ts(3),
        "type": "HL7ParseError",
        "message": "Segment PID is missing required field PID.3 (Patient ID)",
        "severity": 3,
        "app": "chemo-hl7-transformer",
        "operation_id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    },
    {
        "timestamp": _ts(7),
        "type": "ServiceBusException",
        "message": "Message lock expired before processing completed",
        "severity": 3,
        "app": "maternity-hl7-sender",
        "operation_id": "b2c3d4e5f6a7b2c3d4e5f6a7b2c3d4e5",
    },
    {
        "timestamp": _ts(12),
        "type": "ConnectionError",
        "message": "Failed to connect to MPI endpoint: connection timed out after 30s",
        "severity": 4,
        "app": "hl7-sender",
        "operation_id": "c3d4e5f6a7b8c3d4e5f6a7b8c3d4e5f6",
    },
    {
        "timestamp": _ts(25),
        "type": "HL7ValidationError",
        "message": "MSH.9 message type ORM^O01 not supported by this transformer",
        "severity": 2,
        "app": "pims-hl7-transformer",
        "operation_id": "d4e5f6a7b8c9d4e5f6a7b8c9d4e5f6a7",
    },
    {
        "timestamp": _ts(41),
        "type": "DeadLetterException",
        "message": "Message moved to dead-letter queue after 10 delivery attempts",
        "severity": 4,
        "app": "werfen-hl7-transformer",
        "operation_id": "e5f6a7b8c9d0e5f6a7b8c9d0e5f6a7b8",
    },
    {
        "timestamp": _ts(58),
        "type": "KeyError",
        "message": "'PV1' segment not found in parsed HL7 message",
        "severity": 3,
        "app": "cav-paris-hl7-server",
        "operation_id": "f6a7b8c9d0e1f6a7b8c9d0e1f6a7b8c9",
    },
    {
        "timestamp": _ts(74),
        "type": "HL7ParseError",
        "message": "Unexpected segment order: EVN must precede PID in ADT^A01",
        "severity": 2,
        "app": "phw-hl7-transformer",
        "operation_id": "a7b8c9d0e1f2a7b8c9d0e1f2a7b8c9d0",
    },
    {
        "timestamp": _ts(95),
        "type": "TimeoutError",
        "message": "Azure Service Bus send operation timed out after 60s",
        "severity": 3,
        "app": "theatres-hl7-server",
        "operation_id": "b8c9d0e1f2a3b8c9d0e1f2a3b8c9d0e1",
    },
    {
        "timestamp": _ts(130),
        "type": "ConnectionError",
        "message": "SSL handshake failed connecting to MPI: certificate verify failed",
        "severity": 4,
        "app": "hl7-sender",
        "operation_id": "c9d0e1f2a3b4c9d0e1f2a3b4c9d0e1f2",
    },
    {
        "timestamp": _ts(190),
        "type": "HL7ValidationError",
        "message": "PID.7 date of birth '19850230' is not a valid date",
        "severity": 2,
        "app": "chemo-hl7-transformer",
        "operation_id": "d0e1f2a3b4c5d0e1f2a3b4c5d0e1f2a3",
    },
]


# ---------------------------------------------------------------------------
# Topics & Subscriptions  (same shape as service_bus.get_topics / get_subscriptions)
# ---------------------------------------------------------------------------


def _sub(name: str, active: int = 0, dlq: int = 0) -> dict:
    return {
        "name": name,
        "status": "Active",
        "active_message_count": active,
        "dead_letter_message_count": dlq,
        "message_count": active + dlq,
    }


DEMO_SUBSCRIPTIONS: dict[str, list[dict]] = {
    "demo-sbt-mpi-hl7-input": [
        _sub("downstream-a", active=0, dlq=0),
        _sub("downstream-b", active=3, dlq=0),
        _sub("downstream-c", active=72, dlq=2),
    ],
    "demo-sbt-wds-hl7-input": [
        _sub("wds-mpi-sender", active=2, dlq=0),
        _sub("wds-wis-transformer", active=14, dlq=1),
    ],
}

DEMO_TOPICS: list[dict] = [
    {
        "name": topic_name,
        "status": "Active",
        "active_message_count": 0,
        "dead_letter_message_count": 0,
        "scheduled_message_count": 0,
        "subscription_count": len(subs),
        "size_in_bytes": sum(s["active_message_count"] for s in subs) * 2048,
        "max_size_in_megabytes": 1024,
    }
    for topic_name, subs in DEMO_SUBSCRIPTIONS.items()
]

DEMO_SUBSCRIPTION_CONSUMERS: dict[str, list[dict]] = {
    "demo-sbt-mpi-hl7-input": [
        {
            "name": "downstream-a",
            "topic": "demo-sbt-mpi-hl7-input",
            "entity_name": "demo-sbt-mpi-hl7-input/downstream-a",
            "consumer_apps": [
                {
                    "app_name": "demo-mpi-downstream-a-sender-ca",
                    "microservice_id": "mpi_downstream_a_sender",
                    "sender_type": "sender",
                    "workflow_id": "mpi-outbound",
                    "flow_ids": ["mpi-outbound"],
                }
            ],
        },
        {
            "name": "downstream-c",
            "topic": "demo-sbt-mpi-hl7-input",
            "entity_name": "demo-sbt-mpi-hl7-input/downstream-c",
            "consumer_apps": [
                {
                    "app_name": "demo-mpi-downstream-c-sender-ca",
                    "microservice_id": "mpi_downstream_c_sender",
                    "sender_type": "sender",
                    "workflow_id": "mpi-outbound",
                    "flow_ids": ["mpi-outbound"],
                }
            ],
        },
    ],
    "demo-sbt-wds-hl7-input": [
        {
            "name": "wds-mpi-sender",
            "topic": "demo-sbt-wds-hl7-input",
            "entity_name": "demo-sbt-wds-hl7-input/wds-mpi-sender",
            "consumer_apps": [
                {
                    "app_name": "demo-wds-hl7sender-ca",
                    "microservice_id": "wds_hl7_sender",
                    "sender_type": "sender",
                    "workflow_id": "wds-to-mpi",
                    "flow_ids": ["wds-to-mpi"],
                }
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Container Apps  (same shape as azure_monitor.get_container_app_metrics)
# ---------------------------------------------------------------------------


def _container_app(name: str, cpu: float, memory_mb: float, replicas: int = 1) -> dict:
    return {
        "name": name,
        "location": "uksouth",
        "cpu_usage": cpu,
        "memory_bytes": int(memory_mb * 1048576),
        "replicas": replicas,
    }


DEMO_CONTAINER_APPS: list[dict] = [
    _container_app("demo-phw-hl7server-ca", cpu=8.4, memory_mb=142.0, replicas=2),
    _container_app("demo-phw-transformer-ca", cpu=14.2, memory_mb=198.5, replicas=2),
    _container_app("demo-chemo-hl7server-ca", cpu=46.8, memory_mb=312.0, replicas=3),
    _container_app("demo-chemo-transformer-ca", cpu=68.5, memory_mb=420.4, replicas=3),
    _container_app("demo-pims-transformer-ca", cpu=22.1, memory_mb=228.0, replicas=2),
    _container_app("demo-mpi-hl7server-ca", cpu=31.0, memory_mb=276.2, replicas=2),
    _container_app("demo-hl7sender-ca", cpu=19.6, memory_mb=184.0, replicas=2),
    _container_app("demo-wds-hl7sender-ca", cpu=11.3, memory_mb=156.8, replicas=1),
]

_DEMO_APPS_BY_NAME: dict[str, dict] = {a["name"]: a for a in DEMO_CONTAINER_APPS}


def get_demo_container_app_history(app_name: str, hours: int = 1) -> dict:
    """Return a lightweight synthetic CPU & memory time-series for a demo Container App."""
    app = _DEMO_APPS_BY_NAME.get(app_name)
    if app is None:
        return {"name": app_name, "timestamps": [], "cpu": [], "memory_mb": []}

    base_cpu = float(app["cpu_usage"])
    base_mem = float(app["memory_bytes"]) / 1048576
    points = 20
    step_seconds = max(60, int((hours * 3600) / points))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    timestamps: list[str] = []
    cpu: list[float] = []
    memory_mb: list[float] = []
    for i in range(points):
        ts = now - timedelta(seconds=step_seconds * (points - 1 - i))
        wave = math.sin(i * 0.6)
        timestamps.append(ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
        cpu.append(round(max(0.5, base_cpu + wave * max(2.0, base_cpu * 0.15)), 2))
        memory_mb.append(round(max(32.0, base_mem + math.cos(i * 0.4) * (base_mem * 0.06)), 2))

    return {"name": app_name, "timestamps": timestamps, "cpu": cpu, "memory_mb": memory_mb}
