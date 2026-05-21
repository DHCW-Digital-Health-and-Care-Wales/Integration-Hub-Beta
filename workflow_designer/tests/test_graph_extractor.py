from workflow_designer.models import MpiOutboundFlowDefinition
from workflow_designer.services.graph_extractor import extract_flow_from_graph


def _make_graph(nodes):
    """Build a minimal Drawflow export dict from a list of (node_type, data) tuples."""
    data = {}
    for i, (name, node_data) in enumerate(nodes, start=1):
        data[str(i)] = {
            "id": i,
            "name": name,
            "data": node_data,
            "inputs": {"input_1": {"connections": []}} if name != "hl7_server" else {},
            "outputs": {"output_1": {"connections": []}} if name not in {"hl7_sender", "subscription_sender"} else {},
        }
    return {"drawflow": {"Home": {"data": data}}}


def _server_data():
    return {
        "source_system": "PHW",
        "mllp_port": 2575,
        "hl7_version": "2.5",
        "sending_app": "252",
        "validation_flow": "phw",
        "health_board": "PHW",
        "enable_message_store": True,
    }


def _subscription_sender_data(health_board: str, workflow_id: str, receiver_host: str):
    return {
        "health_board": health_board,
        "peer_service": "MPI",
        "workflow_id": workflow_id,
        "receiver_host": receiver_host,
        "receiver_port": 2576,
        "ack_timeout_seconds": 5,
        "max_messages_per_minute": 30,
    }


def test_extract_direct_flow() -> None:
    graph = _make_graph(
        [
            ("hl7_server", _server_data()),
            ("hl7_sender", {"mode": "shared", "destination": "MPI", "destination_port": 2576}),
        ]
    )

    flow, errors = extract_flow_from_graph(graph, "phw-to-mpi")

    assert errors == []
    assert flow is not None
    assert flow.flow_id == "phw-to-mpi"
    assert flow.has_transformer is False
    assert flow.has_dedicated_sender is False
    assert flow.destination == "MPI"


def test_extract_transform_shared_sender() -> None:
    graph = _make_graph(
        [
            ("hl7_server", _server_data()),
            ("hl7_transformer", {"image_name": "phw-hl7transformer"}),
            ("hl7_sender", {"mode": "shared", "destination": "MPI", "destination_port": 2576}),
        ]
    )

    flow, errors = extract_flow_from_graph(graph, "phw-to-mpi")

    assert errors == []
    assert flow is not None
    assert flow.has_transformer is True
    assert flow.has_dedicated_sender is False
    assert flow.transformer_image_name == "phw-hl7transformer"


def test_extract_transform_dedicated_sender() -> None:
    graph = _make_graph(
        [
            ("hl7_server", _server_data()),
            ("hl7_transformer", {"image_name": "pims-hl7transformer"}),
            (
                "hl7_sender",
                {
                    "mode": "dedicated",
                    "destination": "MPI",
                    "destination_host": "mpi.internal",
                    "destination_port": 2576,
                },
            ),
        ]
    )

    flow, errors = extract_flow_from_graph(graph, "pims-to-mpi")

    assert errors == []
    assert flow is not None
    assert flow.has_transformer is True
    assert flow.has_dedicated_sender is True
    assert flow.destination_host == "mpi.internal"
    assert flow.destination_port == 2576


def test_subscription_extractor() -> None:
    graph = _make_graph(
        [
            ("hl7_server", {**_server_data(), "source_system": "MPI", "validation_flow": "mpi", "health_board": "MPI"}),
            ("subscription_sender", _subscription_sender_data("MPI-SWW", "sww-to-chemo", "sww.receiver.local")),
            ("subscription_sender", _subscription_sender_data("MPI-ABU", "abu-to-chemo", "abu.receiver.local")),
        ]
    )

    flow, errors = extract_flow_from_graph(graph, "mpi-outbound")

    assert errors == []
    assert isinstance(flow, MpiOutboundFlowDefinition)
    assert flow.flow_id == "mpi-outbound"
    assert flow.pattern == "Subscription Fan-out"
    assert len(flow.subscription_senders) == 2
    assert flow.subscription_senders[0].subscription_name_ref == "local.servicebus_subscription_mpi_sww_sender_name"
    assert flow.subscription_senders[1].workflow_id == "abu-to-chemo"


def test_subscription_validation_errors() -> None:
    graph = _make_graph(
        [
            ("hl7_server", {**_server_data(), "source_system": "MPI", "validation_flow": "mpi", "health_board": "MPI"}),
            (
                "subscription_sender",
                {
                    "health_board": "",
                    "peer_service": "MPI",
                    "workflow_id": "",
                    "receiver_host": "",
                },
            ),
        ]
    )

    flow, errors = extract_flow_from_graph(graph, "mpi-outbound")

    assert flow is None
    assert any("Subscription Sender 1: 'health_board' is required." == error for error in errors)
    assert any("Subscription Sender 1: 'workflow_id' is required." == error for error in errors)
    assert any("Subscription Sender 1: 'receiver_host' is required." == error for error in errors)


def test_missing_server_returns_errors() -> None:
    graph = _make_graph(
        [
            ("hl7_transformer", {"image_name": "phw-hl7transformer"}),
            ("hl7_sender", {"mode": "shared", "destination": "MPI"}),
        ]
    )

    flow, errors = extract_flow_from_graph(graph, "phw-to-mpi")

    assert flow is None
    assert errors
    assert "Exactly one HL7 Server is required" in errors[0]


def test_missing_sender_returns_errors() -> None:
    graph = _make_graph(
        [
            ("hl7_server", _server_data()),
            ("hl7_transformer", {"image_name": "phw-hl7transformer"}),
        ]
    )

    flow, errors = extract_flow_from_graph(graph, "phw-to-mpi")

    assert flow is None
    assert errors
    assert any("Exactly one Sender is required" in error for error in errors)


def test_empty_graph_returns_errors() -> None:
    flow, errors = extract_flow_from_graph({"drawflow": {"Home": {"data": {}}}}, "empty-flow")

    assert flow is None
    assert errors
    assert any("Exactly one HL7 Server is required" in error for error in errors)
    assert any("Exactly one Sender is required" in error for error in errors)
