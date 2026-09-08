from __future__ import annotations

import configparser
import logging
import os
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    connection_string: str | None
    ingress_queue_name: str | None
    # kw_only + default so these can be added without shifting the positional
    # argument order of any existing (non-topic) caller across the codebase.
    ingress_topic_name: str | None = field(default=None, kw_only=True)
    ingress_subscription_name: str | None = field(default=None, kw_only=True)
    ingress_session_id: str | None
    egress_queue_name: str | None
    egress_session_id: str | None
    service_bus_namespace: str | None
    workflow_id: str | None
    microservice_id: str | None
    health_check_hostname: str | None
    health_check_port: int | None

    def __post_init__(self) -> None:
        _validate_ingress_config(
            self.ingress_queue_name,
            self.ingress_topic_name,
            self.ingress_subscription_name,
        )

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env(
                "SERVICE_BUS_CONNECTION_STRING", required=False
            ),
            ingress_queue_name=(_read_env("INGRESS_QUEUE_NAME", required=False) or "").strip()
            or None,
            ingress_topic_name=(_read_env("INGRESS_TOPIC_NAME", required=False) or "").strip()
            or None,
            ingress_subscription_name=(
                _read_env("INGRESS_SUBSCRIPTION_NAME", required=False) or ""
            ).strip()
            or None,
            ingress_session_id=_read_env("INGRESS_SESSION_ID", required=False),
            egress_queue_name=_read_env("EGRESS_QUEUE_NAME", required=True),
            egress_session_id=_read_env("EGRESS_SESSION_ID", required=False),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE", required=False),
            workflow_id=_read_env("WORKFLOW_ID", required=True),
            microservice_id=_read_env("MICROSERVICE_ID", required=True),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST", required=False),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT", required=False),
        )


@dataclass
class TransformerConfig(AppConfig):
    MAX_BATCH_SIZE: int

    @classmethod
    def from_env_and_config_file(cls, config_path: str) -> "TransformerConfig":
        logger = logging.getLogger(__name__)
        app_config = AppConfig.read_env_config()

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found at path: {config_path}")

        config = configparser.ConfigParser()
        config.read(config_path)
        logger.debug(f"Config file read from {config_path}")

        MAX_BATCH_SIZE = 1
        if config.has_option("DEFAULT", "MAX_BATCH_SIZE"):
            try:
                MAX_BATCH_SIZE = config.getint("DEFAULT", "MAX_BATCH_SIZE")
                logger.debug(f"MAX_BATCH_SIZE set to {MAX_BATCH_SIZE} from config file")
            except ValueError as e:
                logger.warning(
                    f"Failed to parse MAX_BATCH_SIZE from config file, using default value of 1: {e}"
                )
        else:
            logger.debug(
                "MAX_BATCH_SIZE not found in config file, using default value of 1"
            )

        return cls(**asdict(app_config), MAX_BATCH_SIZE=MAX_BATCH_SIZE)


def _validate_ingress_config(
    ingress_queue_name: str | None,
    ingress_topic_name: str | None,
    ingress_subscription_name: str | None,
) -> None:
    """Ensure ingress is configured as exactly one of: a queue, or a topic+subscription pair."""
    has_queue = bool(ingress_queue_name)
    has_topic = bool(ingress_topic_name) or bool(ingress_subscription_name)

    if has_queue and has_topic:
        raise RuntimeError(
            "Invalid ingress configuration: INGRESS_QUEUE_NAME cannot be set together with "
            "INGRESS_TOPIC_NAME/INGRESS_SUBSCRIPTION_NAME. Configure only one ingress transport."
        )

    if not has_queue and not has_topic:
        raise RuntimeError(
            "Missing required configuration: set either INGRESS_QUEUE_NAME, or both "
            "INGRESS_TOPIC_NAME and INGRESS_SUBSCRIPTION_NAME."
        )

    if has_topic and (not ingress_topic_name or not ingress_subscription_name):
        raise RuntimeError(
            "Missing required configuration: INGRESS_TOPIC_NAME and INGRESS_SUBSCRIPTION_NAME "
            "must both be set when using topic-based ingress."
        )


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
