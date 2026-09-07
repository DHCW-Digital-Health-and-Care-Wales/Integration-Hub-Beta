import uuid
from datetime import datetime

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message

from rest_server.hl7.api_constant import ApiConstants


class HL7AckBuilder:
    """Builds the raw HL7 ACK / NACK strings returned to the REST caller.

    The exact wire format is fixed by the API contract, so the ACK is assembled
    as a string (rather than via hl7apy's strict message model). The Integration
    Hub always identifies itself as ``DHCW`` / ``cymru.nhs.uk`` in MSH.3 / MSH.4,
    echoing the inbound sender into MSH.5 / MSH.6.
    """

    def build_success_ack(self, msg: Message) -> str:
        """Application Accept (AA) ACK echoing the inbound message's control ID."""
        return self._build_ack(
            sending_application=get_hl7_field_value(msg.msh, "msh_3.msh_3_1"),
            sending_facility=get_hl7_field_value(msg.msh, "msh_4.msh_4_1"),
            message_control_id=get_hl7_field_value(msg.msh, "msh_10"),
            message_version=get_hl7_field_value(msg.msh, "msh_12") or ApiConstants.DEFAULT_HL7_VERSION,
            ack_code=ApiConstants.ACK_CODE_ACCEPT,
            text=ApiConstants.SUCCESS_MESSAGE,
        )

    def build_validation_nack(self, msg: Message, reason: str) -> str:
        """Application Error (AR) NACK echoing the parsed message's MSH fields."""
        return self._build_ack(
            sending_application=get_hl7_field_value(msg.msh, "msh_3.msh_3_1"),
            sending_facility=get_hl7_field_value(msg.msh, "msh_4.msh_4_1"),
            message_control_id=get_hl7_field_value(msg.msh, "msh_10") or self.generate_message_control_id(),
            message_version=get_hl7_field_value(msg.msh, "msh_12") or ApiConstants.DEFAULT_HL7_VERSION,
            ack_code=ApiConstants.ACK_CODE_REJECT,
            text=reason,
        )

    def build_generic_nack(self, reason: str) -> str:
        """Application Error (AE) NACK with a generated control ID.

        Used when the inbound message cannot be parsed, so no MSH fields can be
        extracted. MSH.3 / MSH.4 are left blank and a fresh MSH.10 is generated.
        """
        return self._build_ack(
            sending_application="",
            sending_facility="",
            message_control_id=self.generate_message_control_id(),
            message_version=ApiConstants.DEFAULT_HL7_VERSION,
            ack_code=ApiConstants.ACK_CODE_ERROR,
            text=reason,
        )

    @staticmethod
    def generate_message_control_id() -> str:
        """Generate a unique control ID no longer than 20 characters (MSH.10 limit)."""
        return uuid.uuid4().hex[: ApiConstants.GENERATED_CONTROL_ID_MAX_LENGTH]

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S")

    def _build_ack(
        self,
        sending_application: str,
        sending_facility: str,
        message_control_id: str,
        message_version: str,
        ack_code: str,
        text: str,
    ) -> str:
        timestamp = self._timestamp()

        msh = (
            f"MSH{ApiConstants.FIELD_SEPARATOR}{ApiConstants.ENCODING_CHARACTERS}"
            f"|{ApiConstants.ACK_SENDING_APPLICATION}|{ApiConstants.ACK_SENDING_FACILITY}"
            f"|{sending_application}|{sending_facility}|{timestamp}||{ApiConstants.ACK_MESSAGE_TYPE_FORMAT}"
            f"|{message_control_id}|{ApiConstants.PROCESSING_ID_PRODUCTION}|{message_version}"
        )
        msa = f"MSA|{ack_code}|{message_control_id}|{text}"

        return f"{msh}{ApiConstants.SEGMENT_SEPARATOR}{msa}"
