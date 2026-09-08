"""CoreReferenceTransformer — translates coded PID reference-data fields via WRDS for RISP -> MPI."""
from __future__ import annotations

import logging
import os

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from transformer_base_lib import BaseTransformer
from wrds_service import WRDSService

from .app_config import WRDSConfig
from .mappers.pid_reference_mapper import apply_core_reference_mapping

logger = logging.getLogger(__name__)

# Only these ADT trigger events are in scope — any other message type passes through unchanged.
# This is a defence-in-depth check: the upstream ingress queue is expected to only carry these
# message types for this flow.
_SUPPORTED_TRIGGER_EVENTS = frozenset({"A28", "A31", "A40"})


class CoreReferenceTransformer(BaseTransformer):

    def __init__(self, wrds_config: WRDSConfig | None = None) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("CoreReference", config_path)

        self._wrds_config = wrds_config or WRDSConfig.read_env_config()
        self._wrds_service = WRDSService(
            endpoint_url=self._wrds_config.endpoint_url,
            timeout_seconds=self._wrds_config.timeout_seconds,
            client_cert_path=self._wrds_config.client_cert_path,
            fixture_file_path=self._wrds_config.local_fixture_path,
        )

    def transform_message(self, hl7_msg: Message) -> Message:
        trigger_event = get_hl7_field_value(hl7_msg.msh, "msh_9.msg_2")
        logger.info("Processing message with trigger event: %s", trigger_event)
        if trigger_event not in _SUPPORTED_TRIGGER_EVENTS:
            return hl7_msg  # not a message type this transformer acts on — pass through unchanged

        return apply_core_reference_mapping(
            hl7_msg, self._wrds_service, self._wrds_config.lookup_table_name
        )
