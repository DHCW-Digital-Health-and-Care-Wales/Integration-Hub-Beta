from __future__ import annotations

import logging
from typing import Any

from message_bus_lib.dead_letter import DeadLetterMessage

from db_sender.db_client import DatabaseClient
from db_sender.handlers.base_handler import BaseDatabaseHandler
from db_sender.msh_extractor import MshInfo
from db_sender.parsers.hl7_id_extractor import extract_pid_identifier_by_authority, get_trigger_event

logger = logging.getLogger(__name__)

NHS_AUTHORITY = "NHS"


class TrrrIdUpdateHandler(BaseDatabaseHandler):
    """Handler for the TRRR NHS-ID update (dbo.TRRRIDUpdate).

    Links a LIMS patient identifier to the patient's NHS number. Routing is done upstream by the
    subscription filter; anything that cannot be mapped is dead-lettered.

    * A31: the LIMS identifier is the PID-3 repetition with the source system authority
      (Service Bus ``SourceSystem``, then MSH-3.1, then ``SOURCE_SYSTEM``; 328 locally, 154 in production).
    * A40: the LIMS identifier is the PID-3 repetition whose authority equals the sending LIMS in MSH-3.1.

    Both take the NHS number from the PID-3 repetition with authority ``NHS``.
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

        if trigger == "A31":
            lims_authority = self._resolve_source_system(metadata, msh_info)
        elif trigger == "A40":
            lims_authority = (msh_info.sending_app or "").strip()
            if not lims_authority:
                logger.error("Missing sending LIMS authority. MessageControlId: %s", msh_info.control_id)
                raise DeadLetterMessage(
                    reason="MissingSendingLimsAuthority",
                    description="Missing sending LIMS authority (MSH-3.1)",
                )
        else:
            logger.error(
                "Unsupported trigger event '%s' for TRRR ID update. MessageControlId: %s",
                trigger,
                msh_info.control_id,
            )
            raise DeadLetterMessage(
                reason="UnsupportedTriggerEvent",
                description=f"Trigger event {trigger} is not supported for TRRR ID update",
            )

        lims_id = extract_pid_identifier_by_authority(message_body, lims_authority)
        if not lims_id:
            logger.error("Missing LIMS identifier. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(
                reason="MissingLimsIdentifier",
                description=f"Missing identifier with authority {lims_authority}",
            )

        nhs_id = extract_pid_identifier_by_authority(message_body, NHS_AUTHORITY)
        if not nhs_id:
            logger.error("Missing NHS identifier. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(
                reason="MissingNhsIdentifier",
                description="Missing NHS identifier",
            )

        logger.debug(
            "Executing %s for %s. MessageControlId: %s",
            self.config.db_stored_procedure,
            trigger,
            msh_info.control_id,
        )

        db_client.execute_trrr_id_update(
            lims_identifier=lims_id,
            new_identifier=nhs_id,
            new_identifier_assigning_authority=NHS_AUTHORITY,
        )

    def _resolve_source_system(self, metadata: dict[str, Any] | None, msh_info: MshInfo) -> str:
        meta = metadata or {}
        sb_source = meta.get("source_system") or meta.get("SourceSystem")
        if sb_source and str(sb_source).strip():
            return str(sb_source).strip()

        if msh_info.sending_app and msh_info.sending_app.strip():
            return msh_info.sending_app.strip()

        return self.config.source_system
