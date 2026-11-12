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


class TrrrMergeHandler(BaseDatabaseHandler):
    """Handler for the TRRR merge (dbo.TRRRIDMerge).

    Processes every A40 (MSH-9.2 = A40): the superseded identifier and authority come from MRG-1, and
    the surviving identifier is the PID-3 repetition whose authority equals the MRG-1 authority.
    Anything else is dead-lettered.
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

        if trigger != "A40":
            logger.error(
                "Unsupported trigger event '%s' for TRRR merge. MessageControlId: %s",
                trigger,
                msh_info.control_id,
            )
            raise DeadLetterMessage(
                reason="UnsupportedTriggerEvent",
                description=f"Trigger event {trigger} is not supported for TRRR merge",
            )

        old_id, old_auth = extract_mrg_identifiers(message_body)
        if not old_id:
            logger.error("Missing old identifier. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(reason="MissingOldIdentifier", description="Missing old identifier")

        if not old_auth:
            logger.error("Missing old assigning authority. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(
                reason="MissingOldAssigningAuthority",
                description="Missing old assigning authority",
            )

        new_id = extract_pid_identifier_by_authority(message_body, old_auth)
        if not new_id:
            logger.error("Missing new identifier. MessageControlId: %s", msh_info.control_id)
            raise DeadLetterMessage(reason="MissingNewIdentifier", description="Missing new identifier")

        logger.debug(
            "Executing %s for A40 merge. MessageControlId: %s",
            self.config.db_stored_procedure,
            msh_info.control_id,
        )

        db_client.execute_trrr_merge(
            old_identifier=old_id,
            old_identifier_assigning_authority=old_auth,
            new_identifier=new_id,
            new_identifier_assigning_authority=old_auth,
        )
