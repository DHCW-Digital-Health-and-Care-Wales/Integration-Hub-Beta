from pathlib import Path

from workflow_designer.models import FlowDefinition, MpiOutboundFlowDefinition, SubscriptionSenderDefinition
from workflow_designer.services.flow_store import FlowStore
from workflow_designer.services.tf_generator import (
    generate_flow_tf,
    generate_locals_snippet,
    generate_subscription_flow_tf,
    generate_subscription_locals_snippet,
    generate_subscription_variables_snippet,
    generate_variables_snippet,
)


def assert_contains(text: str, expected: str) -> None:
    if expected not in text:
        raise AssertionError(f"Expected to find {expected!r} in output.")


def assert_not_contains(text: str, unexpected: str) -> None:
    if unexpected in text:
        raise AssertionError(f"Did not expect to find {unexpected!r} in output.")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_generate_direct_flow_contains_shared_sender_pattern() -> None:
    flow = FlowDefinition(
        flow_id="paris-to-mpi",
        source_system="PARIS",
        mllp_port=2577,
        hl7_version="2.5.1",
        sending_app="169",
        validation_flow="paris",
        health_board="PARIS",
        destination="MPI",
        has_transformer=False,
        destination_host="mpi.internal",
    )

    result = generate_flow_tf(flow)

    assert_contains(result, 'container_apps_paris_to_mpi')
    assert_contains(result, 'servicebus_queue_sender_name')
    assert_contains(result, 'OUTPUT_SESSION_ID    = "mpi"')
    assert_not_contains(result, 'resource "azurerm_servicebus_queue" "paris_to_mpi_queues"')
    assert_not_contains(result, 'hl7_transformer')


def test_generate_transform_shared_sender_flow_contains_transformer_queue() -> None:
    flow = FlowDefinition(
        flow_id="phw-to-mpi",
        source_system="PHW",
        mllp_port=2575,
        hl7_version="2.5",
        sending_app="252",
        validation_flow="phw",
        health_board="PHW",
        destination="MPI",
        has_transformer=True,
        transformer_image_name="phw-hl7transformer",
    )

    result = generate_flow_tf(flow)
    locals_snippet = generate_locals_snippet(flow)

    assert_contains(result, 'phw_hl7_transformer')
    assert_contains(result, 'servicebus_queues_phw_to_mpi')
    assert_contains(result, 'local.servicebus_queue_phw_to_mpi_transformer_name')
    assert_contains(result, 'local.servicebus_queue_sender_id')
    assert_contains(locals_snippet, 'servicebus_queue_phw_to_mpi_transformer_name')
    assert_not_contains(locals_snippet, 'servicebus_queue_phw_to_mpi_sender_name')


def test_generate_transform_dedicated_sender_flow_contains_full_queue_chain() -> None:
    flow = FlowDefinition(
        flow_id="pims-to-mpi",
        source_system="PIMS",
        mllp_port=2579,
        hl7_version="2.3.1",
        sending_app="PIMS",
        validation_flow="pims",
        health_board="PIMS",
        destination="MPI",
        has_transformer=True,
        transformer_image_name="pims-hl7transformer",
        has_dedicated_sender=True,
        destination_host="mpi.internal",
        destination_port=2576,
    )

    flow_tf = generate_flow_tf(flow)
    locals_snippet = generate_locals_snippet(flow)
    variables_snippet = generate_variables_snippet(flow)

    assert_contains(flow_tf, 'pims_hl7_sender')
    assert_contains(flow_tf, 'servicebus_queue_pims_to_mpi_sender_name')
    assert_contains(flow_tf, 'Azure Service Bus Data Receiver')
    assert_contains(flow_tf, 'DESTINATION_HOST = "mpi.internal"')
    assert_contains(locals_snippet, 'container_app_pims_to_mpi_hl7_sender_name')
    assert_contains(variables_snippet, 'deploy_pims_to_mpi_flow')
    assert_contains(variables_snippet, 'stop_pims_to_mpi_flow_apps')


def test_subscription_tf_generator() -> None:
    flow = MpiOutboundFlowDefinition(
        flow_id="mpi-outbound",
        source_system="MPI",
        mllp_port=2580,
        hl7_version="2.5",
        sending_app="MPI",
        validation_flow="mpi",
        health_board="MPI",
        subscription_senders=[
            SubscriptionSenderDefinition(
                health_board="MPI-SWW",
                peer_service="MPI",
                workflow_id="sww-to-chemo",
                receiver_host="sww.receiver.local",
            ),
            SubscriptionSenderDefinition(
                health_board="MPI-ABU",
                peer_service="MPI",
                workflow_id="abu-to-chemo",
                receiver_host="abu.receiver.local",
                max_messages_per_minute=45,
            ),
        ],
    )

    flow_tf = generate_subscription_flow_tf(flow)
    locals_snippet = generate_subscription_locals_snippet(flow)
    variables_snippet = generate_subscription_variables_snippet(flow)

    assert_contains(flow_tf, 'resource "azurerm_servicebus_topic" "mpi_outbound_topics"')
    assert_contains(flow_tf, 'resource "azurerm_servicebus_subscription" "mpi_outbound_subscriptions"')
    assert_contains(flow_tf, 'EGRESS_TOPIC_NAME    = local.servicebus_topic_mpi_outbound_name')
    assert_contains(flow_tf, 'INGRESS_SUBSCRIPTION_NAME = local.servicebus_subscription_mpi_sww_sender_name')
    assert_contains(flow_tf, 'hl7subsndr')
    assert_contains(flow_tf, 'requires_session   = each.value.requires_session')
    assert_contains(flow_tf, 'Azure Service Bus Data Receiver')
    assert_contains(locals_snippet, 'servicebus_topic_mpi_outbound_name')
    assert_contains(locals_snippet, 'servicebus_subscription_mpi_sww_sender_name')
    assert_contains(locals_snippet, 'container_app_mpi_outbound_mpi_sww_hl7_subscription_sender_name')
    assert_contains(variables_snippet, 'deploy_mpi_outbound_flow')


def test_flow_store_seeds_default_flows(tmp_path: Path) -> None:
    json_path = tmp_path / 'flows.json'

    store = FlowStore(str(json_path))
    flows = store.get_all()

    assert_true(json_path.exists(), 'Expected the seeded flows.json file to exist.')
    assert_true(len(flows) == 5, 'Expected the store to seed five default flows.')
    assert_true(all(flow.readonly for flow in flows), 'Expected all seeded flows to be read-only.')
    assert_true(any(flow.flow_id == 'paris-to-mpi' for flow in flows), 'Expected paris-to-mpi to be seeded.')
