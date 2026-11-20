from __future__ import annotations

import os
from dataclasses import dataclass

from lims_trrr_mapper.identifier_mapper import SUPPORTED_MAPPING_TYPES


@dataclass
class AppConfig:
    connection_string: str | None
    service_bus_namespace: str | None
    ingress_topic_name: str
    ingress_subscription_name: str
    ingress_session_id: str | None
    egress_topic_name: str
    egress_session_id: str
    mapping_type: str

    workflow_id: str
    microservice_id: str
    health_board: str
    peer_service: str
    health_check_hostname: str | None
    health_check_port: int | None
    log_level: str
    max_batch_size: int

    @staticmethod
    def read_env_config() -> "AppConfig":
        # No default: each deployment of this image is either the NHS-ID mapper or the merge mapper,
        # and silently picking one would publish the wrong request type.
        mapping_type = _read_required_env("TRRR_MAPPING_TYPE").upper()
        if mapping_type not in SUPPORTED_MAPPING_TYPES:
            supported = ", ".join(sorted(SUPPORTED_MAPPING_TYPES))
            raise ValueError(f"Invalid TRRR_MAPPING_TYPE '{mapping_type}'. Supported: {supported}")

        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            ingress_topic_name=_read_required_env("INGRESS_TOPIC_NAME"),
            ingress_subscription_name=_read_required_env("INGRESS_SUBSCRIPTION_NAME"),
            ingress_session_id=_read_env("INGRESS_SESSION_ID"),
            egress_topic_name=_read_required_env("EGRESS_TOPIC_NAME"),
            # Required: the TRRR sender subscriptions are session-enabled and every sender locks this exact
            # value, so a missing or different value would leave the published requests stuck.
            egress_session_id=_read_required_env("EGRESS_SESSION_ID"),
            mapping_type=mapping_type,
            workflow_id=_read_env("WORKFLOW_ID") or "lims-to-trrr",
            microservice_id=_read_env("MICROSERVICE_ID") or "lims_trrr_mapper",
            health_board=_read_env("HEALTH_BOARD") or "SHARED",
            peer_service=_read_env("PEER_SERVICE") or "TRRR",
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            log_level=_read_env("LOG_LEVEL") or "INFO",
            max_batch_size=_read_int_env("MAX_BATCH_SIZE") or 10,
        )


def _read_env(name: str) -> str | None:
    val = os.getenv(name)
    if val is not None and val.strip() == "":
        return None
    return val


def _read_required_env(name: str) -> str:
    val = os.getenv(name)
    if val is not None and val.strip() != "":
        return val.strip()
    raise RuntimeError(f"Missing required configuration: {name}")


def _read_int_env(name: str) -> int | None:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return None
    try:
        return int(val.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for configuration: {name}") from exc
