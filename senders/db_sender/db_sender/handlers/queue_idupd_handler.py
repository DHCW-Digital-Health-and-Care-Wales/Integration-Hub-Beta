from __future__ import annotations

import logging
from typing import Any

from message_bus_lib.dead_letter import DeadLetterMessage

from db_sender.db_client import DatabaseClient
from db_sender.handlers.base_handler import BaseDatabaseHandler
from db_sender.msh_extractor import MshInfo
from db_sender.parsers.hl7_id_extractor import (
    extract_mrg_identifiers,
    extract_pid_identifier_by_authority,
    get_trigger_event,
)

logger = logging.getLogger(__name__)


class QueueIdUpdateHandler(BaseDatabaseHandler):
    """Handler for WRRS Queue ID Update (dbo.prQueueIdUpdate).

    Processes A31 (patient identifier link / NHS number allocation) and A40 (patient merge)
    messages by extracting patient identifiers and assigning authorities from the raw HL7 payload.
    """

    def handle_message(
        self,
        message_body: str,
        metadata: dict[str, Any],
        msh_info: MshInfo,
        db_client: DatabaseClient,
    ) -> None:
        trigger = msh_info.trigger_event
        if not trigger or trigger == "UNKNOWN":
            trigger = get_trigger_event(message_body)

        if trigger == "A40":
            self._handle_a40(message_body, msh_info, db_client)
        elif trigger == "A31":
            self._handle_a31(message_body, metadata, msh_info, db_client)
        else:
            logger.error(
                "Unsupported trigger event '%s' for Queue ID Update. MessageControlId: %s",
                trigger,
                msh_info.control_id,
            )
            raise DeadLetterMessage(
                reason="UnsupportedTriggerEvent",
                description=f"Trigger event {trigger} is not supported for Queue ID Update",
            )

    def _handle_a40(
        self,
        message_body: str,
        msh_info: MshInfo,
        db_client: DatabaseClient,
    ) -> None:
        old_id, old_auth = extract_mrg_identifiers(message_body)

        if not old_id:
            logger.error("Missing old identifier. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(
                reason="MissingOldIdentifier",
                description="Missing old identifier",
            )

        if not old_auth:
            logger.error("Missing old assigning authority. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(
                reason="MissingOldAssigningAuthority",
                description="Missing old assigning authority",
            )

        new_id = extract_pid_identifier_by_authority(message_body, old_auth)
        if not new_id:
            logger.error("Missing new identifier. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(
                reason="MissingNewIdentifier",
                description="Missing new identifier",
            )

        logger.debug(
            "Executing %s for A40 merge. MessageControlId: %s",
            self.config.db_stored_procedure,
            msh_info.control_id,
        )

        db_client.execute_queue_id_update(
            provider_patient_identifier=None,
            provider_assigning_authority=old_auth,
            old_identifier=old_id,
            old_identifier_assigning_authority=old_auth,
            new_identifier=new_id,
            new_identifier_assigning_authority=old_auth,
        )

    def _handle_a31(
        self,
        message_body: str,
        metadata: dict[str, Any],
        msh_info: MshInfo,
        db_client: DatabaseClient,
    ) -> None:
        source_system = self._resolve_source_system(metadata, msh_info)

        provider_id = extract_pid_identifier_by_authority(message_body, source_system)
        if not provider_id:
            logger.error("Missing LIMS identifier. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(
                reason="MissingLimsIdentifier",
                description=f"Missing identifier with authority {source_system}",
            )

        nhs_id = extract_pid_identifier_by_authority(message_body, "NHS")
        if not nhs_id:
            logger.error("Missing NHS identifier. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(
                reason="MissingNhsIdentifier",
                description="Missing NHS identifier",
            )

        logger.debug(
            "Executing %s for A31 update. MessageControlId: %s",
            self.config.db_stored_procedure,
            msh_info.control_id,
        )

        db_client.execute_queue_id_update(
            provider_patient_identifier=provider_id,
            provider_assigning_authority=source_system,
            old_identifier=None,
            old_identifier_assigning_authority=None,
            new_identifier=nhs_id,
            new_identifier_assigning_authority="NHS",
        )

    def _resolve_source_system(self, metadata: dict[str, Any] | None, msh_info: MshInfo) -> str:
        if metadata:
            sb_source = metadata.get("source_system") or metadata.get("SourceSystem")
            if sb_source and str(sb_source).strip():
                return str(sb_source).strip()

        if msh_info.sending_app and msh_info.sending_app.strip():
            return msh_info.sending_app.strip()

        return self.config.source_system
