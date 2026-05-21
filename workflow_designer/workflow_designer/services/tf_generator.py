from __future__ import annotations

from jinja2 import Environment, select_autoescape

from workflow_designer.models import FlowDefinition, MpiOutboundFlowDefinition

_TEMPLATE_ENV = Environment(
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=select_autoescape(enabled_extensions=("html", "xml"), default_for_string=False, default=False),
)

_FLOW_TEMPLATE = _TEMPLATE_ENV.from_string(
    """locals {
  {{ fv }}_enabled = var.deploy_apps && var.deploy_{{ fv }}_flow

  container_apps_{{ fv }} = local.{{ fv }}_enabled ? {
    {{ fs }}_hl7_server = {
      name             = local.container_app_{{ fv }}_hl7_server_name
      container_name   = "{{ fs }}-hl7-server"
      image            = "{{ dollar }}{var.acr_name}.azurecr.io/hl7_server:{{ dollar }}{var.image_tag}"
      cpu              = 0.5
      memory           = "1Gi"
      min_replicas     = 1
      max_replicas     = 2
      target_port      = {{ flow.mllp_port }}
      external_enabled = true
      transport        = "tcp"
      env = {
        FLOW_ID              = "{{ flow.flow_id }}"
        SOURCE_SYSTEM        = "{{ flow.source_system }}"
        DESTINATION_SYSTEM   = "{{ flow.destination }}"
        HL7_VERSION          = "{{ flow.hl7_version }}"
        SENDING_APP          = "{{ flow.sending_app }}"
        VALIDATION_FLOW      = "{{ flow.validation_flow }}"
        HEALTH_BOARD         = "{{ flow.health_board }}"
        OUTPUT_QUEUE_NAME    = {{ server_output_queue_name }}
        OUTPUT_SESSION_ID    = "{{ server_output_session_id }}"
        ENABLE_MESSAGE_STORE = "{{ enable_message_store }}"
{% if include_server_destination %}        DESTINATION_HOST       = "{{ flow.destination_host }}"
        DESTINATION_PORT       = "{{ flow.destination_port }}"
{% endif %}      }
    }
{% if flow.has_transformer %}
    {{ fs }}_hl7_transformer = {
      name           = local.container_app_{{ fv }}_hl7_transformer_name
      container_name = "{{ fs }}-hl7-transformer"
      image          = "{{ dollar }}{var.acr_name}.azurecr.io/{{ transformer_image }}:{{ dollar }}{var.image_tag}"
      cpu            = 0.5
      memory         = "1Gi"
      min_replicas   = 1
      max_replicas   = 2
      env = {
        FLOW_ID           = "{{ flow.flow_id }}"
        SOURCE_SYSTEM     = "{{ flow.source_system }}"
        INPUT_QUEUE_NAME  = local.servicebus_queue_{{ fv }}_transformer_name
        OUTPUT_QUEUE_NAME = {{ transformer_output_queue_name }}
        INPUT_SESSION_ID  = "{{ flow.flow_id }}"
        OUTPUT_SESSION_ID = "{{ transformer_output_session_id }}"
      }
    }
{% endif %}
{% if flow.has_dedicated_sender %}
    {{ fs }}_hl7_sender = {
      name           = local.container_app_{{ fv }}_hl7_sender_name
      container_name = "{{ fs }}-hl7-sender"
      image          = "{{ dollar }}{var.acr_name}.azurecr.io/hl7_sender:{{ dollar }}{var.image_tag}"
      cpu            = 0.5
      memory         = "1Gi"
      min_replicas   = 1
      max_replicas   = 2
      env = {
        FLOW_ID          = "{{ flow.flow_id }}"
        SOURCE_SYSTEM    = "{{ flow.source_system }}"
        INPUT_QUEUE_NAME = local.servicebus_queue_{{ fv }}_sender_name
        SESSION_ID       = "{{ flow.flow_id }}"
        DESTINATION_HOST = "{{ flow.destination_host }}"
        DESTINATION_PORT = "{{ flow.destination_port }}"
      }
    }
{% endif %}  } : {}

  servicebus_queues_{{ fv }} = local.{{ fv }}_enabled ? {
{% for queue in queues %}    {{ queue.key }} = {
      name                  = {{ queue.name_ref }}
      max_size_in_megabytes = 1024
      requires_session      = true
    }
{% endfor %}  } : {}

  {{ fv }}_queue_permissions_flat = local.{{ fv }}_enabled ? flatten([
{% for principal_name, permissions in permissions_by_principal.items() %}    [
{% for permission in permissions %}      {
        key                  = "{{ permission.key }}"
        principal_id         = module.container_apps_{{ fv }}.principal_ids["{{ permission.principal_key }}"]
        role_definition_name = "{{ permission.role }}"
        scope                = {{ permission.scope }}
      },
{% endfor %}    ],
{% endfor %}  ]) : []
}

module "container_apps_{{ fv }}" {
  source = "../../modules/container-apps"

  enabled        = local.{{ fv }}_enabled
  container_apps = local.container_apps_{{ fv }}
  tags           = local.tags
}
{% if queues %}
resource "azurerm_servicebus_queue" "{{ fv }}_queues" {
  for_each = local.servicebus_queues_{{ fv }}

  name                  = each.value.name
  namespace_id          = local.servicebus_namespace_id
  max_size_in_megabytes = each.value.max_size_in_megabytes
  requires_session      = each.value.requires_session
  default_message_ttl   = "P14D"
  lock_duration         = "PT5M"
}
{% endif %}
resource "azurerm_role_assignment" "{{ fv }}_queue_permissions" {
  for_each = {
    for permission in local.{{ fv }}_queue_permissions_flat :
    permission.key => permission
  }

  scope                = each.value.scope
  role_definition_name = each.value.role_definition_name
  principal_id         = each.value.principal_id
}

resource "azapi_resource_action" "stop_{{ fv }}_apps" {
  for_each = var.stop_{{ fv }}_flow_apps && local.{{ fv }}_enabled ? {
    for app_name, app_id in module.container_apps_{{ fv }}.container_app_ids :
    app_name => app_id
  } : {}

  type        = "Microsoft.App/containerApps@2023-05-01"
  resource_id = each.value
  action      = "stop"
  method      = "POST"
}
"""
)

_SUBSCRIPTION_FLOW_TEMPLATE = _TEMPLATE_ENV.from_string(
    """locals {
  {{ fv }}_enabled = var.deploy_apps && var.deploy_{{ fv }}_flow

  container_apps_{{ fv }} = local.{{ fv }}_enabled ? {
    {{ fs }}_hl7_server = {
      name             = local.container_app_{{ fv }}_hl7_server_name
      container_name   = "{{ fs }}-hl7-server"
      image            = "{{ dollar }}{var.acr_name}.azurecr.io/hl7_server:{{ dollar }}{var.image_tag}"
      cpu              = 0.5
      memory           = "1Gi"
      min_replicas     = 1
      max_replicas     = 2
      target_port      = {{ flow.mllp_port }}
      external_enabled = true
      transport        = "tcp"
      env = {
        FLOW_ID              = "{{ flow.flow_id }}"
        SOURCE_SYSTEM        = "{{ flow.source_system }}"
        HL7_VERSION          = "{{ flow.hl7_version }}"
        SENDING_APP          = "{{ flow.sending_app }}"
        VALIDATION_FLOW      = "{{ flow.validation_flow }}"
        HEALTH_BOARD         = "{{ flow.health_board }}"
        EGRESS_TOPIC_NAME    = local.servicebus_topic_{{ fv }}_name
        EGRESS_SESSION_ID    = "mpi-outbound"
        ENABLE_MESSAGE_STORE = "{{ enable_message_store }}"
      }
    }
{% for sender in senders %}    {{ sender.app_key }} = {
      name           = {{ sender.container_app_name_ref }}
      container_name = "{{ sender.container_slug }}-hl7subsender"
      image          = "{{ dollar }}{var.acr_name}.azurecr.io/hl7subsndr:{{ dollar }}{var.image_tag}"
      cpu            = 0.5
      memory         = "1Gi"
      min_replicas   = 1
      max_replicas   = 2
      env = {
        INGRESS_TOPIC_NAME        = local.servicebus_topic_{{ fv }}_name
        INGRESS_SUBSCRIPTION_NAME = {{ sender.subscription_name_ref }}
        INGRESS_SESSION_ID        = "mpi-outbound"
        RECEIVER_MLLP_HOST        = "{{ sender.receiver_host }}"
        RECEIVER_MLLP_PORT        = "{{ sender.receiver_port }}"
        WORKFLOW_ID               = "{{ sender.workflow_id }}"
        MICROSERVICE_ID           = {{ sender.container_app_name_ref }}
        HEALTH_BOARD              = "{{ sender.health_board }}"
        PEER_SERVICE              = "{{ sender.peer_service }}"
        ACK_TIMEOUT_SECONDS       = "{{ sender.ack_timeout_seconds }}"
        MAX_MESSAGES_PER_MINUTE   = "{{ sender.max_messages_per_minute }}"
      }
    }
{% endfor %}  } : {}

  servicebus_topics_{{ fv }} = local.{{ fv }}_enabled ? {
    input = {
      name                  = local.servicebus_topic_{{ fv }}_name
      max_size_in_megabytes = 1024
    }
  } : {}

  servicebus_subscriptions_{{ fv }} = local.{{ fv }}_enabled ? {
{% for sender in senders %}    {{ sender.slug }} = {
      name              = {{ sender.subscription_name_ref }}
      topic_key         = "input"
      requires_session  = true
      max_delivery_count = 5
    }
{% endfor %}  } : {}

  {{ fv }}_topic_permissions_flat = local.{{ fv }}_enabled ? [
{% for permission in permissions %}    {
      key                  = "{{ permission.key }}"
      principal_id         = module.container_apps_{{ fv }}.principal_ids["{{ permission.principal_key }}"]
      role_definition_name = "{{ permission.role }}"
      scope                = azurerm_servicebus_topic.{{ fv }}_topics["input"].id
    },
{% endfor %}  ] : []
}

module "container_apps_{{ fv }}" {
  source = "../../modules/container-apps"

  enabled        = local.{{ fv }}_enabled
  container_apps = local.container_apps_{{ fv }}
  tags           = local.tags
}

resource "azurerm_servicebus_topic" "{{ fv }}_topics" {
  for_each = local.servicebus_topics_{{ fv }}

  name                  = each.value.name
  namespace_id          = local.servicebus_namespace_id
  max_size_in_megabytes = each.value.max_size_in_megabytes
  default_message_ttl   = "P14D"
}

resource "azurerm_servicebus_subscription" "{{ fv }}_subscriptions" {
  for_each = local.servicebus_subscriptions_{{ fv }}

  name               = each.value.name
  topic_id           = azurerm_servicebus_topic.{{ fv }}_topics[each.value.topic_key].id
  requires_session   = each.value.requires_session
  max_delivery_count = each.value.max_delivery_count
}

resource "azurerm_role_assignment" "{{ fv }}_topic_permissions" {
  for_each = {
    for permission in local.{{ fv }}_topic_permissions_flat :
    permission.key => permission
  }

  scope                = each.value.scope
  role_definition_name = each.value.role_definition_name
  principal_id         = each.value.principal_id
}

resource "azapi_resource_action" "stop_{{ fv }}_apps" {
  for_each = var.stop_{{ fv }}_flow_apps && local.{{ fv }}_enabled ? {
    for app_name, app_id in module.container_apps_{{ fv }}.container_app_ids :
    app_name => app_id
  } : {}

  type        = "Microsoft.App/containerApps@2023-05-01"
  resource_id = each.value
  action      = "stop"
  method      = "POST"
}
"""
)

_LOCALS_TEMPLATE = _TEMPLATE_ENV.from_string(
    (
        "container_app_{{ fv }}_hl7_server_name      = "
        "\"{{ dollar }}{var.primary_region_infix}-{{ dollar }}{var.environment}-{{ source_slug }}-hl7server-ca\"\n"
        "{% if flow.has_transformer %}"
        "container_app_{{ fv }}_hl7_transformer_name = "
        "\"{{ dollar }}{var.primary_region_infix}-{{ dollar }}{var.environment}-{{ source_slug }}-hl7transformer-ca\"\n"
        "{% endif %}"
        "{% if flow.has_dedicated_sender %}"
        "container_app_{{ fv }}_hl7_sender_name      = "
        "\"{{ dollar }}{var.primary_region_infix}-{{ dollar }}{var.environment}-{{ source_slug }}-hl7sender-ca\"\n"
        "{% endif %}"
        "{% if flow.has_transformer %}"
        "servicebus_queue_{{ fv }}_transformer_name = "
        "lower(\"{{ dollar }}{local.servicebus_namespace_name}-SBQ-{{ source_system_title }}-HL7-Transformer\")\n"
        "{% endif %}"
        "{% if flow.has_dedicated_sender %}"
        "servicebus_queue_{{ fv }}_sender_name      = "
        "lower(\"{{ dollar }}{local.servicebus_namespace_name}-SBQ-{{ source_system_title }}-HL7-Sender\")\n"
        "{% endif %}"
    )
)

_SUBSCRIPTION_LOCALS_TEMPLATE = _TEMPLATE_ENV.from_string(
    (
        "container_app_{{ fv }}_hl7_server_name = "
        "\"{{ dollar }}{var.primary_region_infix}-{{ dollar }}{var.environment}-{{ source_slug }}-hl7server-ca\"\n"
        "servicebus_topic_{{ fv }}_name         = "
        "lower(\"{{ dollar }}{local.servicebus_namespace_name}-SBT-{{ source_system_title }}-HL7-Input\")\n"
        "{% for sender in senders %}"
        "servicebus_subscription_{{ sender.slug }}_sender_name = "
        "lower(\"{{ dollar }}{local.servicebus_namespace_name}-SBS-{{ sender.health_board }}-Sender\")\n"
        "container_app_{{ fv }}_{{ sender.slug }}_hl7_subscription_sender_name = "
        "\"{{ dollar }}{var.primary_region_infix}-{{ dollar }}{var.environment}-{{ sender.slug }}-hl7subsender-ca\"\n"
        "{% endfor %}"
    )
)

_VARIABLES_TEMPLATE = _TEMPLATE_ENV.from_string(
    """variable "deploy_{{ fv }}_flow" {
  type        = bool
  description = "Whether to deploy the {{ flow.flow_id }} flow"
  default     = true
}

variable "stop_{{ fv }}_flow_apps" {
  type        = bool
  description = "Whether to stop the {{ flow.flow_id }} flow apps after deployment."
  default     = false
}
"""
)


_SUBSCRIPTION_VARIABLES_TEMPLATE = _VARIABLES_TEMPLATE


def _queue_resource_scope(flow_var_name: str, queue_key: str) -> str:
    return f'azurerm_servicebus_queue.{flow_var_name}_queues["{queue_key}"].id'


def _build_context(flow: FlowDefinition) -> dict[str, object]:
    fv = flow.flow_var_name
    fs = flow.source_slug
    queues: list[dict[str, str]] = []
    permissions_by_principal: dict[str, list[dict[str, str]]] = {}

    if flow.has_transformer:
        queues.append(
            {
                "key": "transformer",
                "name_ref": f"local.servicebus_queue_{fv}_transformer_name",
            }
        )
        server_output_queue_name = f"local.servicebus_queue_{fv}_transformer_name"
        server_output_session_id = flow.flow_id
    else:
        server_output_queue_name = "local.servicebus_queue_sender_name"
        server_output_session_id = "mpi"

    if flow.has_dedicated_sender:
        queues.append(
            {
                "key": "sender",
                "name_ref": f"local.servicebus_queue_{fv}_sender_name",
            }
        )

    permissions_by_principal[f"{fs}_hl7_server"] = [
        {
            "key": f"{fs}-hl7-server-output",
            "principal_key": f"{fs}_hl7_server",
            "role": "Azure Service Bus Data Sender",
            "scope": (
                _queue_resource_scope(fv, "transformer")
                if flow.has_transformer
                else "local.servicebus_queue_sender_id"
            ),
        }
    ]

    if flow.enable_message_store:
        permissions_by_principal[f"{fs}_hl7_server"].append(
            {
                "key": f"{fs}-hl7-server-message-store",
                "principal_key": f"{fs}_hl7_server",
                "role": "Azure Service Bus Data Sender",
                "scope": "local.servicebus_queue_message_store_id",
            }
        )

    transformer_output_queue_name = "local.servicebus_queue_sender_name"
    transformer_output_session_id = "mpi"

    if flow.has_transformer:
        permissions_by_principal[f"{fs}_hl7_transformer"] = [
            {
                "key": f"{fs}-hl7-transformer-input",
                "principal_key": f"{fs}_hl7_transformer",
                "role": "Azure Service Bus Data Receiver",
                "scope": _queue_resource_scope(fv, "transformer"),
            }
        ]

        if flow.has_dedicated_sender:
            transformer_output_queue_name = f"local.servicebus_queue_{fv}_sender_name"
            transformer_output_session_id = flow.flow_id
            permissions_by_principal[f"{fs}_hl7_transformer"].append(
                {
                    "key": f"{fs}-hl7-transformer-output",
                    "principal_key": f"{fs}_hl7_transformer",
                    "role": "Azure Service Bus Data Sender",
                    "scope": _queue_resource_scope(fv, "sender"),
                }
            )
            permissions_by_principal[f"{fs}_hl7_sender"] = [
                {
                    "key": f"{fs}-hl7-sender-input",
                    "principal_key": f"{fs}_hl7_sender",
                    "role": "Azure Service Bus Data Receiver",
                    "scope": _queue_resource_scope(fv, "sender"),
                }
            ]
        else:
            permissions_by_principal[f"{fs}_hl7_transformer"].append(
                {
                    "key": f"{fs}-hl7-transformer-output",
                    "principal_key": f"{fs}_hl7_transformer",
                    "role": "Azure Service Bus Data Sender",
                    "scope": "local.servicebus_queue_sender_id",
                }
            )

    return {
        "dollar": "$",
        "flow": flow,
        "fv": fv,
        "fs": fs,
        "transformer_image": flow.transformer_image_name or f"{fs}-hl7transformer",
        "queues": queues,
        "permissions_by_principal": permissions_by_principal,
        "server_output_queue_name": server_output_queue_name,
        "server_output_session_id": server_output_session_id,
        "transformer_output_queue_name": transformer_output_queue_name,
        "transformer_output_session_id": transformer_output_session_id,
        "enable_message_store": str(flow.enable_message_store).lower(),
        "include_server_destination": (not flow.has_transformer) or flow.has_dedicated_sender,
        "source_slug": flow.source_slug,
        "source_system_title": flow.source_system,
    }


def _build_subscription_context(flow: MpiOutboundFlowDefinition) -> dict[str, object]:
    fv = flow.flow_var_name
    fs = flow.source_slug
    senders = [
        {
            "slug": sender.slug,
            "container_slug": sender.slug.replace("_", "-"),
            "health_board": sender.health_board,
            "peer_service": sender.peer_service,
            "workflow_id": sender.workflow_id,
            "receiver_host": sender.receiver_host,
            "receiver_port": sender.receiver_port,
            "ack_timeout_seconds": sender.ack_timeout_seconds,
            "max_messages_per_minute": sender.max_messages_per_minute,
            "subscription_name_ref": sender.subscription_name_ref,
            "container_app_name_ref": f"local.container_app_{fv}_{sender.slug}_hl7_subscription_sender_name",
            "app_key": f"{sender.slug}_hl7_subscription_sender",
        }
        for sender in flow.subscription_senders
    ]
    permissions = [
        {
            "key": f"{fs}-hl7-server-topic-sender",
            "principal_key": f"{fs}_hl7_server",
            "role": "Azure Service Bus Data Sender",
        },
        *[
            {
                "key": f"{sender.slug}-hl7subsender-topic-receiver",
                "principal_key": f"{sender.slug}_hl7_subscription_sender",
                "role": "Azure Service Bus Data Receiver",
            }
            for sender in flow.subscription_senders
        ],
    ]
    return {
        "dollar": "$",
        "flow": flow,
        "fv": fv,
        "fs": fs,
        "senders": senders,
        "permissions": permissions,
        "enable_message_store": str(flow.enable_message_store).lower(),
        "source_slug": flow.source_slug,
        "source_system_title": flow.source_system,
    }


def generate_flow_tf(flow: FlowDefinition) -> str:
    return _FLOW_TEMPLATE.render(**_build_context(flow)).strip() + "\n"


def generate_locals_snippet(flow: FlowDefinition) -> str:
    return _LOCALS_TEMPLATE.render(**_build_context(flow)).strip() + "\n"


def generate_variables_snippet(flow: FlowDefinition) -> str:
    return _VARIABLES_TEMPLATE.render(**_build_context(flow)).strip() + "\n"


def generate_subscription_flow_tf(flow: MpiOutboundFlowDefinition) -> str:
    return _SUBSCRIPTION_FLOW_TEMPLATE.render(**_build_subscription_context(flow)).strip() + "\n"


def generate_subscription_locals_snippet(flow: MpiOutboundFlowDefinition) -> str:
    return _SUBSCRIPTION_LOCALS_TEMPLATE.render(**_build_subscription_context(flow)).strip() + "\n"


def generate_subscription_variables_snippet(flow: MpiOutboundFlowDefinition) -> str:
    return _SUBSCRIPTION_VARIABLES_TEMPLATE.render(**_build_subscription_context(flow)).strip() + "\n"
