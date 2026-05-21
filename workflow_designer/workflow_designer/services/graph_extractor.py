"""Converts a Drawflow graph export into a flow definition."""
from __future__ import annotations

import logging
import re
from typing import Any

from workflow_designer.models import FlowDefinition, MpiOutboundFlowDefinition, SubscriptionSenderDefinition

log = logging.getLogger(__name__)
FLOW_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _get_nodes(graph_json: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        return graph_json["drawflow"]["Home"]["data"], []
    except (KeyError, TypeError):
        return None, ["Invalid graph data — missing drawflow.Home.data."]


def _validate_server_data(server_data: dict[str, Any], errors: list[str]) -> None:
    for field in (
        "source_system",
        "mllp_port",
        "hl7_version",
        "sending_app",
        "validation_flow",
        "health_board",
    ):
        if not str(server_data.get(field, "")).strip():
            errors.append(f"HL7 Server: '{field}' is required.")


def _parse_int(value: Any, field_name: str, errors: list[str], default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{field_name} must be an integer.")
        return default


def extract_subscription_flow_from_graph(
    graph_json: dict[str, Any],
    flow_id: str,
) -> tuple[MpiOutboundFlowDefinition | None, list[str]]:
    nodes, graph_errors = _get_nodes(graph_json)
    if graph_errors:
        return None, graph_errors
    assert nodes is not None

    errors: list[str] = []
    server_nodes = [node for node in nodes.values() if node.get("name") == "hl7_server"]
    transformer_nodes = [node for node in nodes.values() if node.get("name") == "hl7_transformer"]
    sender_nodes = [node for node in nodes.values() if node.get("name") == "hl7_sender"]
    subscription_sender_nodes = [node for node in nodes.values() if node.get("name") == "subscription_sender"]

    if len(server_nodes) != 1:
        errors.append(f"Exactly one HL7 Server is required (found {len(server_nodes)}).")
    if len(subscription_sender_nodes) < 1:
        errors.append("At least one Subscription Sender is required.")
    if sender_nodes:
        errors.append("Subscription flows do not support standard HL7 Sender nodes.")
    if transformer_nodes:
        errors.append("Subscription flows do not support Transformer nodes.")
    if not FLOW_ID_PATTERN.fullmatch(flow_id):
        errors.append("Flow ID must be kebab-case, e.g. my-flow-name.")
    if errors:
        return None, errors

    server_data = server_nodes[0].get("data", {})
    _validate_server_data(server_data, errors)

    subscription_senders: list[SubscriptionSenderDefinition] = []
    for index, node in enumerate(subscription_sender_nodes, start=1):
        sender_data = node.get("data", {})
        for field in ("health_board", "peer_service", "workflow_id", "receiver_host"):
            if not str(sender_data.get(field, "")).strip():
                errors.append(f"Subscription Sender {index}: '{field}' is required.")

        subscription_senders.append(
            SubscriptionSenderDefinition(
                health_board=str(sender_data.get("health_board", "")).strip().upper(),
                peer_service=str(sender_data.get("peer_service", "MPI")).strip().upper() or "MPI",
                workflow_id=str(sender_data.get("workflow_id", "")).strip().lower(),
                receiver_host=str(sender_data.get("receiver_host", "")).strip(),
                receiver_port=_parse_int(
                    sender_data.get("receiver_port", 2576),
                    f"Subscription Sender {index}: receiver_port",
                    errors,
                    2576,
                ),
                ack_timeout_seconds=_parse_int(
                    sender_data.get("ack_timeout_seconds", 5),
                    f"Subscription Sender {index}: ack_timeout_seconds",
                    errors,
                    5,
                ),
                max_messages_per_minute=_parse_int(
                    sender_data.get("max_messages_per_minute", 30),
                    f"Subscription Sender {index}: max_messages_per_minute",
                    errors,
                    30,
                ),
            )
        )

    if errors:
        return None, errors

    flow = MpiOutboundFlowDefinition(
        flow_id=flow_id,
        source_system=str(server_data["source_system"]).strip().upper(),
        mllp_port=_parse_int(server_data.get("mllp_port", 2575), "HL7 Server: mllp_port", errors, 2575),
        hl7_version=str(server_data.get("hl7_version", "2.5")).strip(),
        sending_app=str(server_data.get("sending_app", "")).strip(),
        validation_flow=str(server_data.get("validation_flow", "")).strip().lower(),
        health_board=str(server_data.get("health_board", "")).strip().upper(),
        enable_message_store=bool(server_data.get("enable_message_store", True)),
        subscription_senders=subscription_senders,
        readonly=False,
    )
    if errors:
        return None, errors
    log.debug("Extracted subscription flow %s from canvas graph", flow.flow_id)
    return flow, []


def extract_flow_from_graph(
    graph_json: dict[str, Any],
    flow_id: str,
) -> tuple[FlowDefinition | MpiOutboundFlowDefinition | None, list[str]]:
    """
    Parse a Drawflow graph JSON export and produce a flow definition.

    Returns (flow, []) on success or (None, [errors]) on failure.
    """
    nodes, graph_errors = _get_nodes(graph_json)
    if graph_errors:
        return None, graph_errors
    assert nodes is not None

    if any(node.get("name") == "subscription_sender" for node in nodes.values()):
        return extract_subscription_flow_from_graph(graph_json, flow_id)

    errors: list[str] = []
    server_nodes = [node for node in nodes.values() if node.get("name") == "hl7_server"]
    transformer_nodes = [node for node in nodes.values() if node.get("name") == "hl7_transformer"]
    sender_nodes = [node for node in nodes.values() if node.get("name") == "hl7_sender"]

    if len(server_nodes) != 1:
        errors.append(f"Exactly one HL7 Server is required (found {len(server_nodes)}).")
    if len(sender_nodes) != 1:
        errors.append(f"Exactly one Sender is required (found {len(sender_nodes)}).")
    if len(transformer_nodes) > 1:
        errors.append(f"At most one Transformer is supported (found {len(transformer_nodes)}).")
    if errors:
        return None, errors

    server = server_nodes[0]
    sender = sender_nodes[0]
    transformer = transformer_nodes[0] if transformer_nodes else None

    server_data = server.get("data", {})
    sender_data = sender.get("data", {})
    transformer_data = transformer.get("data", {}) if transformer else {}

    has_transformer = transformer is not None
    has_dedicated_sender = sender_data.get("mode", "shared") == "dedicated"

    _validate_server_data(server_data, errors)

    if has_transformer and not str(transformer_data.get("image_name", "")).strip():
        errors.append("Transformer: 'image_name' is required.")

    if has_dedicated_sender and not str(sender_data.get("destination_host", "")).strip():
        errors.append("Dedicated Sender: 'destination_host' is required.")

    if not FLOW_ID_PATTERN.fullmatch(flow_id):
        errors.append("Flow ID must be kebab-case, e.g. my-flow-name.")

    if errors:
        return None, errors

    mllp_port = _parse_int(server_data.get("mllp_port", 2575), "HL7 Server: mllp_port", errors, 2575)
    destination_port = _parse_int(sender_data.get("destination_port", 2576), "Sender: destination_port", errors, 2576)
    if errors:
        return None, errors

    flow = FlowDefinition(
        flow_id=flow_id,
        source_system=str(server_data["source_system"]).strip().upper(),
        mllp_port=mllp_port,
        hl7_version=str(server_data.get("hl7_version", "2.5")).strip(),
        sending_app=str(server_data.get("sending_app", "")).strip(),
        validation_flow=str(server_data.get("validation_flow", "")).strip().lower(),
        health_board=str(server_data.get("health_board", "")).strip().upper(),
        destination=str(sender_data.get("destination", "MPI")).strip().upper() or "MPI",
        has_transformer=has_transformer,
        transformer_image_name=str(transformer_data.get("image_name", "")).strip() if has_transformer else "",
        has_dedicated_sender=has_dedicated_sender,
        destination_host=str(sender_data.get("destination_host", "")).strip() if has_dedicated_sender else "",
        destination_port=destination_port if has_dedicated_sender else 2576,
        enable_message_store=bool(server_data.get("enable_message_store", True)),
        readonly=False,
    )
    log.debug("Extracted flow %s from canvas graph", flow.flow_id)
    return flow, []
