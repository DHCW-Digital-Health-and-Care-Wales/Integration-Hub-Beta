"""
Container App discovery — builds flow definitions from Container App environment variables.

Each Container App in the Integration Hub has standardised env vars that
describe how it connects to Azure Service Bus:

- ``WORKFLOW_ID`` — identifies the flow this app belongs to
- ``EGRESS_QUEUE_NAME`` / ``EGRESS_TOPIC_NAME`` — Service Bus destination
- ``INGRESS_QUEUE_NAME`` / ``INGRESS_TOPIC_NAME`` — Service Bus source
- ``INGRESS_SUBSCRIPTION_NAME`` — topic subscription (subscription senders)

This module queries the Container Apps Management API, reads those env vars
from every deployed app, groups apps into flows, and constructs a complete set
of flow definitions — replacing the need for hardcoded queue suffix patterns.

Flow membership comes from the ``integration-hub-flow`` Container App tag (a
comma-separated list of flow IDs, each of which must be some deployed app's
``WORKFLOW_ID``), otherwise from the app's own ``WORKFLOW_ID``. A shared
publisher (e.g. the WDS server feeding the WDS→MPI, WDS→WIS and WDS→PHW
subscriptions) lists every flow it feeds, so it appears in each of them.
``WORKFLOW_ID`` remains the telemetry identity used by alarms.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping
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
        "WRRS_TOPIC_NAME",
        "INGRESS_QUEUE_NAME",
        "INGRESS_TOPIC_NAME",
        "INGRESS_SUBSCRIPTION_NAME",
        # Sender destination — used to populate real host:port targets for the
        # network connectivity test page (see dashboard.services.network_test).
        "RECEIVER_MLLP_HOST",
        "RECEIVER_MLLP_PORT",
    }
)

# Env vars naming topics an app publishes to. The RISP REST server publishes
# WRRS-bound messages to a second topic alongside its EGRESS_TOPIC_NAME.
_EGRESS_TOPIC_ENV_VARS = ("EGRESS_TOPIC_NAME", "WRRS_TOPIC_NAME")

# Container App tag holding a comma-separated list of the flow IDs an app
# belongs to. Azure tag names are case-insensitive.
FLOW_TAG = "integration-hub-flow"

# Same shape as the flow IDs accepted by the alarm config and pause routes.
_FLOW_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,119}")

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
    "lims-to-hub": {
        "label": "LIMS → Hub",
        "source": "LIMS",
        "destination": "MPI / TRRR",
        "colour": "#14b8a6",
        "icon": "bi-hospital",
    },
    "lims-to-trrr": {
        "label": "LIMS → TRRR",
        "source": "LIMS",
        "destination": "TRRR",
        "colour": "#0d9488",
        "icon": "bi-database",
    },
    "lims-to-wrrs": {
        "label": "LIMS → WRRS",
        "source": "LIMS",
        "destination": "WRRS",
        "colour": "#2dd4bf",
        "icon": "bi-database",
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
    "wds-to-phw": {
        "label": "WDS → PHW",
        "source": "WDS",
        "destination": "PHW",
        "colour": "#fb923c",
        "icon": "bi-heart-pulse",
    },
    "risp-to-mpi": {
        "label": "RISP → MPI",
        "source": "RISP",
        "destination": "MPI",
        "colour": "#6366f1",
        "icon": "bi-clipboard2-data",
        "transformer": "Core Reference Transformer",
    },
    "risp-to-wrrs": {
        "label": "RISP → WRRS",
        "source": "RISP",
        "destination": "WRRS",
        "colour": "#818cf8",
        "icon": "bi-database",
    },
    "pms-to-mpi": {
        "label": "PMS → MPI",
        "source": "PMS",
        "destination": "MPI",
        "colour": "#84cc16",
        "icon": "bi-hospital",
    },
    "cav-pms-to-wcrs": {
        "label": "CAV PMS → WCRS",
        "source": "PMS",
        "destination": "WCRS",
        "colour": "#65a30d",
        "icon": "bi-database",
    },
    "mpi-to-topic": {
        "label": "MPI Outbound",
        "source": "MPI",
        "destination": "Downstream Systems",
        "colour": "#f59e0b",
        "icon": "bi-broadcast",
    },
    "sww-to-chemo": {
        "label": "MPI → SWW ChemoCare",
        "source": "MPI",
        "destination": "SWW ChemoCare",
        "colour": "#eab308",
        "icon": "bi-capsule",
    },
    "bcu-to-chemo": {
        "label": "MPI → BCU ChemoCare",
        "source": "MPI",
        "destination": "BCU ChemoCare",
        "colour": "#ca8a04",
        "icon": "bi-capsule",
    },
    "mpi-to-phw": {
        "label": "MPI → PHW",
        "source": "MPI",
        "destination": "PHW",
        "colour": "#d97706",
        "icon": "bi-heart-pulse",
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


def _get_tag(tags: Mapping[str, str] | None, name: str) -> str | None:
    """Return a tag value by case-insensitive name (Azure tag names are case-insensitive)."""
    for key, value in (tags or {}).items():
        if key.lower() == name.lower():
            return value
    return None


def parse_flow_tag(tag_value: str | None) -> list[str]:
    """Parse a comma-separated flow tag: entries are trimmed, lower-cased and de-duplicated; invalid IDs are dropped."""
    flow_ids: list[str] = []
    for raw in (tag_value or "").split(","):
        flow_id = raw.strip().lower()
        if _FLOW_ID_RE.fullmatch(flow_id) and flow_id not in flow_ids:
            flow_ids.append(flow_id)
    return flow_ids


def resolve_flow_ids(tagged_flow_ids: list[str], workflow_id: str, known_workflow_ids: set[str]) -> list[str]:
    """Return the flows an app belongs to.

    Tagged flow IDs are kept only if some deployed app has that ``WORKFLOW_ID``. Alarm rules, pauses and telemetry are
    keyed by ``WORKFLOW_ID``, so every flow must be one; this also stops a stale tag (for example the old
    ``mpi-outbound`` value) from inventing a flow. A tagged app need not list its own ``WORKFLOW_ID``: the MPI server
    (``mpi-to-topic``) only lists the downstream flows it feeds. With no usable tag entries the app belongs to its
    ``WORKFLOW_ID`` flow.
    """
    known = {wid.lower(): wid for wid in known_workflow_ids}
    flow_ids = [known[flow_id] for flow_id in tagged_flow_ids if flow_id in known]
    ignored = [flow_id for flow_id in tagged_flow_ids if flow_id not in known]
    if ignored:
        log.info("Ignoring %s tag entries with no matching WORKFLOW_ID: %s", FLOW_TAG, ", ".join(ignored))
    return flow_ids or [workflow_id]


def app_flow_ids(app: Mapping) -> list[str]:
    """Return the flow IDs a discovered app belongs to (falls back to its ``WORKFLOW_ID``)."""
    flow_ids = app.get("flow_ids")
    if flow_ids:
        return list(flow_ids)
    workflow_id = (app.get("env") or {}).get("WORKFLOW_ID")
    return [workflow_id] if workflow_id else []


def _egress_topics(env: Mapping[str, str]) -> list[str]:
    """Return every topic an app publishes to, in ``_EGRESS_TOPIC_ENV_VARS`` order."""
    return [topic for name in _EGRESS_TOPIC_ENV_VARS if (topic := env.get(name))]


def _list_container_apps() -> list[dict]:
    """Query all Container Apps and extract flow-relevant env vars.

    Returns a list of dicts, one per app, with keys:
    ``name``, ``env`` (dict of flow env vars), ``target_port``, ``fqdn`` and
    ``flow_tag`` (parsed flow IDs from the flow tag, see :func:`parse_flow_tag`).
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
                    "flow_tag": parse_flow_tag(_get_tag(app.tags, FLOW_TAG)),
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
    """Build a single flow definition from the apps that belong to flow ``workflow_id``."""
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
    # Prefer a topic this flow's servers publish to *and* its consumers read, so a
    # server shared by several flows over different topics (RISP publishes to an
    # MPI topic and a WRRS topic) is shown against the topic this flow uses.
    server_topics = [t for srv in servers for t in _egress_topics(srv["env"])]
    consumer_topics = [
        t for app in subscription_senders + subscription_transformers if (t := app["env"].get("INGRESS_TOPIC_NAME"))
    ]
    topic = next((t for t in server_topics if t in consumer_topics), None)
    if not topic:
        topic = next(iter(server_topics + consumer_topics), None)

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

    This only applies when the publisher's ``integration-hub-flow`` tag does not
    list the consumer's flow; a tagged publisher joins that flow, giving it a
    ``source_port`` so it is kept as a flow in its own right.
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
    env vars and flow tag, groups them by flow ID (an app shared by several
    flows joins each of them), and builds a flow definition for each group.

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

            # Resolve flow membership, then group by flow ID; a shared app is listed under every flow it belongs to.
            known_workflow_ids = {app["env"]["WORKFLOW_ID"] for app in apps}
            groups: dict[str, list[dict]] = {}
            for app in apps:
                app["flow_ids"] = resolve_flow_ids(
                    app.get("flow_tag") or [], app["env"]["WORKFLOW_ID"], known_workflow_ids
                )
                for flow_id in app["flow_ids"]:
                    groups.setdefault(flow_id, []).append(app)

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
        egress_topics = [t.lower() for t in _egress_topics(env)]
        ingress_subscription = (env.get("INGRESS_SUBSCRIPTION_NAME") or "").lower()

        matches = False
        if entity_type_lower == "queue":
            matches = lower in (ingress, egress)
        elif entity_type_lower == "topic":
            matches = lower == ingress_topic or lower in egress_topics
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
                    "flow_ids": app_flow_ids(app),
                }
            ],
        }
        consumers_by_topic.setdefault(topic_name, []).append(entry)

    return consumers_by_topic
