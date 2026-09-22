"""
Container App discovery — builds flow definitions from Container App environment variables.

Each Container App in the Integration Hub has standardised env vars that
describe how it connects to Azure Service Bus:

- ``WORKFLOW_ID`` — identifies the flow this app belongs to
- ``EGRESS_QUEUE_NAME`` / ``EGRESS_TOPIC_NAME`` — Service Bus destination
- ``INGRESS_QUEUE_NAME`` / ``INGRESS_TOPIC_NAME`` — Service Bus source
- ``INGRESS_SUBSCRIPTION_NAME`` — topic subscription (subscription senders)

This module queries the Container Apps Management API, reads those env vars
from every deployed app, groups apps by ``WORKFLOW_ID``, and constructs a
complete set of flow definitions — replacing the need for hardcoded queue
suffix patterns.
"""

from __future__ import annotations

import logging
import time
from threading import Lock

from azure.mgmt.appcontainers import ContainerAppsAPIClient

from dashboard import config
from dashboard.services.credentials import get_azure_credential

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Env var names to extract from Container Apps
# ---------------------------------------------------------------------------

_FLOW_ENV_VARS = frozenset(
    {
        "WORKFLOW_ID",
        "MICROSERVICE_ID",
        "EGRESS_QUEUE_NAME",
        "EGRESS_TOPIC_NAME",
        "INGRESS_QUEUE_NAME",
        "INGRESS_TOPIC_NAME",
        "INGRESS_SUBSCRIPTION_NAME",
        # Sender destination — used to populate real host:port targets for the
        # network connectivity test page (see dashboard.services.network_test).
        "RECEIVER_MLLP_HOST",
        "RECEIVER_MLLP_PORT",
    }
)

# ---------------------------------------------------------------------------
# Display metadata for known flows
#
# Auto-discovered flows without an entry here get a label derived from their
# WORKFLOW_ID and a colour from the rotating palette.
# ---------------------------------------------------------------------------

_DISPLAY_META: dict[str, dict] = {
    "phw-to-mpi": {
        "label": "PHW → MPI",
        "source": "PHW",
        "destination": "MPI",
        "colour": "#3b82f6",
        "icon": "bi-heart-pulse",
        "transformer": "PHW Transformer",
    },
    "paris-to-mpi": {
        "label": "Paris → MPI",
        "source": "Paris",
        "destination": "MPI",
        "colour": "#a855f7",
        "icon": "bi-activity",
    },
    "mosaiq-to-mpi": {
        "label": "Mosaiq → MPI",
        "source": "Mosaiq",
        "destination": "MPI",
        "colour": "#ec4899",
        "icon": "bi-radioactive",
    },
    "chemocare-to-mpi": {
        "label": "ChemoCare → MPI",
        "source": "ChemoCare",
        "destination": "MPI",
        "colour": "#06b6d4",
        "icon": "bi-capsule",
        "transformer": "Chemo Transformer",
    },
    "pims-to-mpi": {
        "label": "PIMS → MPI",
        "source": "PIMS",
        "destination": "MPI",
        "colour": "#22c55e",
        "icon": "bi-clipboard2-pulse",
        "transformer": "PIMS Transformer",
    },
    "wds-to-mpi": {
        "label": "WDS → MPI",
        "source": "WDS",
        "destination": "MPI",
        "colour": "#f97316",
        "icon": "bi-hospital",
    },
    "wds-to-wis": {
        "label": "WDS → WIS",
        "source": "WDS",
        "destination": "WIS",
        "colour": "#0ea5e9",
        "icon": "bi-send",
        "transformer": "WDS Transformer",
    },
    "mpi-to-topic": {
        "label": "MPI Outbound",
        "source": "MPI",
        "destination": "Downstream Systems",
        "colour": "#f59e0b",
        "icon": "bi-broadcast",
    },
}

_AUTO_COLOURS = ["#ec4899", "#8b5cf6", "#14b8a6", "#ef4444", "#64748b"]

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 300
_cache_lock = Lock()
_cached_flows: dict[str, dict] = {}
_cached_apps: list[dict] = []
_cache_timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Container App querying
# ---------------------------------------------------------------------------


def _is_configured() -> bool:
    return all(
        [
            config.AZURE_SUBSCRIPTION_ID,
            config.AZURE_CONTAINER_APPS_RESOURCE_GROUP,
        ]
    )


def _list_container_apps() -> list[dict]:
    """Query all Container Apps and extract flow-relevant env vars.

    Returns a list of dicts, one per app, with keys:
    ``name``, ``env`` (dict of flow env vars), ``target_port``.
    Only apps that have a ``WORKFLOW_ID`` env var are included.
    """
    cred = get_azure_credential()
    client = ContainerAppsAPIClient(cred, config.AZURE_SUBSCRIPTION_ID)
    apps = client.container_apps.list_by_resource_group(
        config.AZURE_CONTAINER_APPS_RESOURCE_GROUP,
    )

    result: list[dict] = []
    for app in apps:
        env_vars: dict[str, str] = {}
        target_port: int | None = None
        fqdn: str | None = None

        # Extract env vars from all containers
        containers = (app.template.containers or []) if app.template else []
        for container in containers:
            for env in container.env or []:
                if env.name in _FLOW_ENV_VARS and env.value:
                    env_vars[env.name] = env.value

        # Extract ingress target port and FQDN (used as the reachable source
        # host:port for HL7 servers on the network connectivity test page)
        if app.configuration and app.configuration.ingress:
            target_port = app.configuration.ingress.target_port
            fqdn = app.configuration.ingress.fqdn

        if env_vars.get("WORKFLOW_ID"):
            result.append(
                {
                    "name": app.name,
                    "env": env_vars,
                    "target_port": target_port,
                    "fqdn": fqdn,
                }
            )

    return result


# ---------------------------------------------------------------------------
# App role classification
# ---------------------------------------------------------------------------


def _classify_app(env: dict[str, str]) -> str:
    """Classify a Container App's role based on its env vars.

    Roles:
    - ``server``: receives HL7 and sends to a queue or topic
    - ``transformer``: reads from one queue, writes to another
    - ``subscription_transformer``: reads from a topic subscription, writes to a queue
    - ``sender``: reads from a queue and delivers HL7 downstream
    - ``subscription_sender``: reads from a topic subscription
    """
    has_ingress_queue = bool(env.get("INGRESS_QUEUE_NAME"))
    has_egress_queue = bool(env.get("EGRESS_QUEUE_NAME"))
    has_egress_topic = bool(env.get("EGRESS_TOPIC_NAME"))
    has_ingress_topic = bool(env.get("INGRESS_TOPIC_NAME"))

    if has_ingress_topic and has_egress_queue:
        return "subscription_transformer"
    if has_ingress_topic:
        return "subscription_sender"
    if has_ingress_queue and has_egress_queue:
        return "transformer"
    if has_ingress_queue and not has_egress_queue:
        return "sender"
    if (has_egress_queue or has_egress_topic) and not has_ingress_queue:
        return "server"
    return "unknown"


# ---------------------------------------------------------------------------
# Flow building
# ---------------------------------------------------------------------------


def _build_flow(workflow_id: str, apps: list[dict]) -> dict:
    """Build a single flow definition from a group of apps sharing a WORKFLOW_ID."""
    servers: list[dict] = []
    transformers: list[dict] = []
    subscription_transformers: list[dict] = []
    senders: list[dict] = []
    subscription_senders: list[dict] = []

    for app in apps:
        role = _classify_app(app["env"])
        if role == "server":
            servers.append(app)
        elif role == "transformer":
            transformers.append(app)
        elif role == "subscription_transformer":
            subscription_transformers.append(app)
        elif role == "sender":
            senders.append(app)
        elif role == "subscription_sender":
            subscription_senders.append(app)

    source_port: int | None = servers[0]["target_port"] if servers else None
    source_host: str | None = servers[0].get("fqdn") if servers else None
    topic: str | None = None
    pre_queue: str | None = None
    post_queue: str | None = None
    transformer_name: str | None = None

    # --- Destination (RECEIVER_MLLP_HOST/PORT, set on senders/subscription senders) ---
    destination_host: str | None = None
    destination_port: int | None = None
    for app in senders + subscription_senders:
        host = app["env"].get("RECEIVER_MLLP_HOST")
        if host:
            destination_host = host
            raw_port = app["env"].get("RECEIVER_MLLP_PORT")
            destination_port = int(raw_port) if raw_port and raw_port.isdigit() else None
            break

    # --- Topic-based flow (e.g. MPI Outbound) ---
    for srv in servers:
        t = srv["env"].get("EGRESS_TOPIC_NAME")
        if t:
            topic = t
            break
    if not topic:
        for ss in subscription_senders:
            t = ss["env"].get("INGRESS_TOPIC_NAME")
            if t:
                topic = t
                break
    if not topic:
        for st in subscription_transformers:
            t = st["env"].get("INGRESS_TOPIC_NAME")
            if t:
                topic = t
                break

    # --- Queue-based flow ---
    # Capture the server's egress queue (used when no transformer in the group)
    server_egress_queue: str | None = None
    for srv in servers:
        q = srv["env"].get("EGRESS_QUEUE_NAME")
        if q:
            server_egress_queue = q
            break

    if transformers:
        t_app = transformers[0]
        pre_queue = t_app["env"].get("INGRESS_QUEUE_NAME")
        post_queue = t_app["env"].get("EGRESS_QUEUE_NAME")
        # Prefer display name from metadata, fall back to Container App name
        meta_tfr = _DISPLAY_META.get(workflow_id, {}).get("transformer")
        if meta_tfr:
            transformer_name = meta_tfr
        else:
            # Derive from app name: strip common prefix/suffix patterns
            raw = t_app["name"]
            transformer_name = raw.replace("-", " ").title()
    elif subscription_transformers:
        st_app = subscription_transformers[0]
        post_queue = st_app["env"].get("EGRESS_QUEUE_NAME")
        meta_tfr = _DISPLAY_META.get(workflow_id, {}).get("transformer")
        if meta_tfr:
            transformer_name = meta_tfr
        else:
            raw = st_app["name"]
            transformer_name = raw.replace("-", " ").title()
    elif senders and not topic:
        # No transformer — server sends directly to sender queue
        post_queue = senders[0]["env"].get("INGRESS_QUEUE_NAME")
    elif server_egress_queue and not topic:
        # Server only (no transformer or sender in this group) —
        # the egress queue is the "post-queue" for dashboard display.
        post_queue = server_egress_queue

    subscriptions: list[dict] = []
    for st in subscription_transformers:
        sub_name = st["env"].get("INGRESS_SUBSCRIPTION_NAME")
        sub_topic = st["env"].get("INGRESS_TOPIC_NAME")
        if not sub_name or not sub_topic:
            continue
        subscriptions.append(
            {
                "name": sub_name,
                "topic": sub_topic,
                "entity_name": f"{sub_topic}/{sub_name}",
                "consumer_apps": [
                    {
                        "app_name": st["name"],
                        "microservice_id": st["env"].get("MICROSERVICE_ID") or st["name"],
                        "sender_type": "subscription_transformer",
                        "workflow_id": workflow_id,
                    }
                ],
            }
        )
    for ss in subscription_senders:
        sub_name = ss["env"].get("INGRESS_SUBSCRIPTION_NAME")
        sub_topic = ss["env"].get("INGRESS_TOPIC_NAME")
        if not sub_name or not sub_topic:
            continue
        subscriptions.append(
            {
                "name": sub_name,
                "topic": sub_topic,
                "entity_name": f"{sub_topic}/{sub_name}",
                "consumer_apps": [
                    {
                        "app_name": ss["name"],
                        "microservice_id": ss["env"].get("MICROSERVICE_ID") or ss["name"],
                        "sender_type": "subscription_sender",
                        "workflow_id": workflow_id,
                    }
                ],
            }
        )

    # Display metadata
    meta = _DISPLAY_META.get(workflow_id, {})
    colour_idx = hash(workflow_id) % len(_AUTO_COLOURS)

    return {
        "label": meta.get("label", workflow_id.replace("-", " ").title()),
        "source": meta.get("source", workflow_id.split("-", maxsplit=1)[0].upper()),
        "source_port": source_port,
        "source_host": source_host,
        "destination_host": destination_host,
        "destination_port": destination_port,
        "pre_queue": pre_queue,
        "transformer": transformer_name,
        "post_queue": post_queue,
        "topic": topic,
        "subscriptions": subscriptions,
        "destination": meta.get("destination", "MPI"),
        "colour": meta.get("colour", _AUTO_COLOURS[colour_idx]),
        "icon": meta.get("icon", "bi-arrow-left-right"),
    }


def _merge_subscription_sender_flows(flows: dict[str, dict]) -> None:
    """Merge subscription-sender-only flows into the flow that owns their topic.

    Some subscription senders have a different ``WORKFLOW_ID`` from the server
    that publishes to the same topic (e.g. ``bcu-to-chemo`` reads from the MPI
    topic owned by ``mpi-to-topic``).  These should not appear as separate flows
    since the dashboard already lists all subscriptions under the topic flow.
    """
    # Map topic → flow_id for flows that have a server (i.e. source_port set)
    topic_owners: dict[str, str] = {}
    for fid, flow in flows.items():
        if flow.get("topic") and flow.get("source_port"):
            topic_owners[flow["topic"]] = fid

    # Remove flows whose only contribution is subscription senders
    to_remove: list[str] = []
    for fid, flow in flows.items():
        topic = flow.get("topic")
        if (
            topic
            and topic in topic_owners
            and topic_owners[topic] != fid
            and not flow.get("source_port")
            and not flow.get("pre_queue")
            and not flow.get("post_queue")
        ):
            to_remove.append(fid)

    for fid in to_remove:
        topic = flows[fid].get("topic")
        owner_id = topic_owners.get(topic) if topic else None
        if owner_id:
            owner = flows[owner_id]
            owner_subs = owner.setdefault("subscriptions", [])
            existing_keys = {
                (
                    sub.get("topic"),
                    sub.get("name"),
                    tuple(app.get("microservice_id") for app in sub.get("consumer_apps", [])),
                )
                for sub in owner_subs
            }
            for sub in flows[fid].get("subscriptions", []):
                key = (
                    sub.get("topic"),
                    sub.get("name"),
                    tuple(app.get("microservice_id") for app in sub.get("consumer_apps", [])),
                )
                if key not in existing_keys:
                    owner_subs.append(sub)
                    existing_keys.add(key)
        log.debug("Merging subscription-sender flow %r into topic owner", fid)
        del flows[fid]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover_flows(force: bool = False) -> dict[str, dict]:
    """Discover flow definitions from Container App environment variables.

    Queries all Container Apps in the configured resource group, reads their
    env vars, groups them by ``WORKFLOW_ID``, and builds a flow definition
    for each group.

    Results are cached for 5 minutes.  Pass ``force=True`` to bypass cache.
    Returns an empty dict if the Container Apps API is unreachable or not
    configured, which lets the caller fall back to static definitions.
    """
    global _cached_flows, _cached_apps, _cache_timestamp  # noqa: PLW0603

    if not _is_configured():
        log.warning("Container Apps not configured — flow discovery disabled")
        return {}

    now = time.monotonic()
    with _cache_lock:
        if not force and _cached_flows and (now - _cache_timestamp) < _CACHE_TTL_SECONDS:
            return dict(_cached_flows)

        try:
            apps = _list_container_apps()
            log.info("Discovered %d Container App(s) with WORKFLOW_ID", len(apps))

            # Group apps by WORKFLOW_ID
            groups: dict[str, list[dict]] = {}
            for app in apps:
                wf_id = app["env"]["WORKFLOW_ID"]
                groups.setdefault(wf_id, []).append(app)

            flows: dict[str, dict] = {}
            for wf_id, group in groups.items():
                flows[wf_id] = _build_flow(wf_id, group)

            # Merge subscription-sender-only flows into the topic owner.
            # Subscription senders with their own WORKFLOW_ID all read from
            # the same topic as a server in another flow.  The dashboard
            # shows subscriptions via Service Bus queries, so these extra
            # flows are redundant.
            _merge_subscription_sender_flows(flows)

            log.info(
                "Built %d flow definition(s): %s",
                len(flows),
                sorted(flows.keys()),
            )
            _cached_flows = flows
            _cached_apps = apps
            _cache_timestamp = now
            return dict(flows)

        except Exception as exc:
            log.error("Container App flow discovery failed: %s", exc)
            # Return stale cache if available, otherwise empty
            return dict(_cached_flows)


def queue_to_microservice_ids(queue_name: str) -> list[str]:
    """Return the ``MICROSERVICE_ID`` values of apps whose INGRESS or EGRESS queue matches *queue_name*.

    Relies on the cached Container App data populated by :func:`discover_flows`.
    Returns an empty list if no match is found.
    """
    return entity_to_microservice_ids("queue", queue_name)


def _split_subscription_entity_name(entity_name: str) -> tuple[str | None, str | None]:
    if "/" not in entity_name:
        return None, None
    raw_topic_name, raw_subscription_name = entity_name.split("/", maxsplit=1)
    topic_name = raw_topic_name.strip() or None
    subscription_name = raw_subscription_name.strip() or None
    return topic_name, subscription_name


def entity_to_microservice_ids(entity_type: str, entity_name: str) -> list[str]:
    """Return microservice IDs related to a queue, topic, or topic subscription."""
    # Ensure discovery has run at least once
    discover_flows()

    entity_type_lower = entity_type.lower()
    lower = entity_name.lower()
    topic_name: str | None = None
    subscription_name: str | None = None
    if entity_type_lower == "subscription":
        topic_name, subscription_name = _split_subscription_entity_name(entity_name)
        if not topic_name or not subscription_name:
            return []
        topic_name_lower = topic_name.lower()
        subscription_name_lower = subscription_name.lower()

    result: list[str] = []
    for app in _cached_apps:
        env = app["env"]
        ingress = (env.get("INGRESS_QUEUE_NAME") or "").lower()
        egress = (env.get("EGRESS_QUEUE_NAME") or "").lower()
        ingress_topic = (env.get("INGRESS_TOPIC_NAME") or "").lower()
        egress_topic = (env.get("EGRESS_TOPIC_NAME") or "").lower()
        ingress_subscription = (env.get("INGRESS_SUBSCRIPTION_NAME") or "").lower()

        matches = False
        if entity_type_lower == "queue":
            matches = lower in (ingress, egress)
        elif entity_type_lower == "topic":
            matches = lower in (ingress_topic, egress_topic)
        elif entity_type_lower == "subscription":
            matches = ingress_topic == topic_name_lower and ingress_subscription == subscription_name_lower

        if matches:
            ms_id = env.get("MICROSERVICE_ID") or app["name"]
            if ms_id not in result:
                result.append(ms_id)
    return result


def get_subscription_consumers_by_topic() -> dict[str, list[dict]]:
    """Return topic -> subscription consumer metadata built from cached Container App discovery."""
    discover_flows()

    consumers_by_topic: dict[str, list[dict]] = {}
    seen: set[tuple[str, str, str]] = set()
    for app in _cached_apps:
        env = app["env"]
        topic_name = env.get("INGRESS_TOPIC_NAME")
        subscription_name = env.get("INGRESS_SUBSCRIPTION_NAME")
        workflow_id = env.get("WORKFLOW_ID")
        if not topic_name or not subscription_name or not workflow_id:
            continue

        key = (topic_name, subscription_name, env.get("MICROSERVICE_ID") or app["name"])
        if key in seen:
            continue
        seen.add(key)

        entry = {
            "name": subscription_name,
            "topic": topic_name,
            "entity_name": f"{topic_name}/{subscription_name}",
            "consumer_apps": [
                {
                    "app_name": app["name"],
                    "microservice_id": env.get("MICROSERVICE_ID") or app["name"],
                    "sender_type": _classify_app(env),
                    "workflow_id": workflow_id,
                }
            ],
        }
        consumers_by_topic.setdefault(topic_name, []).append(entry)

    return consumers_by_topic
