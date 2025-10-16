from __future__ import annotations

import configparser
import logging
import os
from dataclasses import asdict, dataclass


logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    connection_string: str | None
    ingress_queue_name: str | None
    ingress_session_id: str | None
    egress_queue_name: str | None
    egress_session_id: str | None
    service_bus_namespace: str | None
    audit_queue_name: str | None
    workflow_id: str | None
    microservice_id: str | None
    health_check_hostname: str | None
    health_check_port: int | None

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env(
                "SERVICE_BUS_CONNECTION_STRING", required=False
            ),
            ingress_queue_name=_read_env("INGRESS_QUEUE_NAME", required=True),
            ingress_session_id=_read_env("INGRESS_SESSION_ID", required=False),
            egress_queue_name=_read_env("EGRESS_QUEUE_NAME", required=True),
            egress_session_id=_read_env("EGRESS_SESSION_ID", required=False),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE", required=False),
            audit_queue_name=_read_env("AUDIT_QUEUE_NAME", required=False),
            workflow_id=_read_env("WORKFLOW_ID", required=True),
            microservice_id=_read_env("MICROSERVICE_ID", required=True),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST", required=False),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT", required=False),
        )


@dataclass
class TransformerConfig(AppConfig):
    MAX_BATCH_SIZE: int

    @classmethod
    def from_env_and_config_file(cls, config_path: str | None) -> "TransformerConfig":
        app_config = AppConfig.read_env_config()

        config = configparser.ConfigParser()
        # MAX_BATCH_SIZE defaults to 1 when not configured to stop the reconnection loop
        MAX_BATCH_SIZE = 1

        if config_path:
            logger.debug(
                "Loading transformer configuration from %s (exists=%s)",
                config_path,
                os.path.exists(config_path),
            )
        else:
            logger.debug(
                "No configuration path provided; using environment configuration only"
            )

        if config_path and os.path.exists(config_path):
            config.read(config_path)
            default_options = config.defaults()
            if default_options:
                raw_batch_size = default_options.get("max_batch_size")
                if raw_batch_size:
                    MAX_BATCH_SIZE = config.getint("DEFAULT", "max_batch_size")

        return cls(**asdict(app_config), MAX_BATCH_SIZE=MAX_BATCH_SIZE)


def _read_env(name: str, required: bool = False) -> str | None:
    value = os.getenv(name)
    if required and (value is None or value.strip() == ""):
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def _read_int_env(name: str, required: bool = False) -> int | None:
    value = os.getenv(name)
    if value is None:
        if required:
            raise RuntimeError(f"Missing required configuration: {name}")
        return None
    return int(value)
