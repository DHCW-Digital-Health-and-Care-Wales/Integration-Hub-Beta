import uuid
from datetime import datetime

from field_utils_lib import get_hl7_field_value
from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.core import Message, Segment

from .hl7_constant import Hl7Constants


class HL7AckBuilder:
    def build_ack(self, message_control_id: str, original_msg: Message) -> Message:
        ack = Message("ACK", validation_level=VALIDATION_LEVEL.STRICT)

        # Build MSH segment
        ack.msh.msh_1 = Hl7Constants.FIELD_SEPARATOR
        ack.msh.msh_2 = Hl7Constants.ENCODING_CHARACTERS
        ack.msh.msh_3 = original_msg.msh.msh_5.value
        ack.msh.msh_4 = original_msg.msh.msh_6.value
        ack.msh.msh_5 = original_msg.msh.msh_3.value
        ack.msh.msh_6 = original_msg.msh.msh_4.value
        ack.msh.msh_7 = datetime.now().strftime("%Y%m%d%H%M%S")
        ack.msh.msh_9.message_code = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        ack.msh.msh_9.trigger_event = original_msg.msh.msh_9.trigger_event.value
        ack.msh.msh_9.message_structure = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        ack.msh.msh_10 = message_control_id
        # HL7 v2.5 section 2.9.2.2 requires MSH-11 to be copied from the initiating message, so a
        # test message is never acknowledged as production. MSH-11 is required in the ACK, so fall
        # back to "P" if the inbound message omitted it.
        ack.msh.msh_11 = get_hl7_field_value(original_msg.msh, "msh_11") or Hl7Constants.PROCESSING_ID_PRODUCTION
        ack.msh.msh_12 = original_msg.msh.msh_12.value

        # Build MSA segment
        msa = Segment("MSA", validation_level=VALIDATION_LEVEL.STRICT)
        msa.msa_1 = Hl7Constants.ACK_CODE_ACCEPT
        msa.msa_2 = message_control_id
        ack.add(msa)

        return ack

    def build_nack(self, message_control_id: str, original_msg: Message, ack_code: str, reason: str) -> Message:
        """Build a NACK (MSA-1 = AR/AE) echoing the original message's MSH fields.

        Used when the inbound message was successfully parsed but processing was later aborted
        (validation failure, or an unexpected error after parsing). TOLERANT validation is used,
        rather than STRICT (as in build_ack), so that building the NACK itself cannot fail even if
        the original message is missing optional fields.
        """
        ack = Message("ACK", validation_level=VALIDATION_LEVEL.TOLERANT)

        # Build MSH segment
        ack.msh.msh_1 = Hl7Constants.FIELD_SEPARATOR
        ack.msh.msh_2 = Hl7Constants.ENCODING_CHARACTERS
        ack.msh.msh_3 = get_hl7_field_value(original_msg.msh, "msh_5")
        ack.msh.msh_4 = get_hl7_field_value(original_msg.msh, "msh_6")
        ack.msh.msh_5 = get_hl7_field_value(original_msg.msh, "msh_3")
        ack.msh.msh_6 = get_hl7_field_value(original_msg.msh, "msh_4")
        ack.msh.msh_7 = datetime.now().strftime("%Y%m%d%H%M%S")
        ack.msh.msh_9.message_code = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        ack.msh.msh_9.trigger_event = get_hl7_field_value(original_msg.msh, "msh_9.msh_9_2")
        ack.msh.msh_9.message_structure = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        ack.msh.msh_10 = message_control_id
        # See build_ack: MSH-11 must be copied from the initiating message, falling back to "P".
        ack.msh.msh_11 = get_hl7_field_value(original_msg.msh, "msh_11") or Hl7Constants.PROCESSING_ID_PRODUCTION
        ack.msh.msh_12 = get_hl7_field_value(original_msg.msh, "msh_12") or Hl7Constants.DEFAULT_HL7_VERSION

        # Build MSA segment
        msa = Segment("MSA", validation_level=VALIDATION_LEVEL.TOLERANT)
        msa.msa_1 = ack_code
        msa.msa_2 = message_control_id
        msa.msa_3 = self._sanitize_reason(reason)
        ack.add(msa)

        return ack

    def build_generic_nack(self, reason: str, message_control_id: str | None = None) -> Message:
        """Build an Application Error (AE) NACK when no original message could be recovered.

        Used when the inbound message cannot be parsed at all (or was rejected before parsing,
        e.g. for exceeding the maximum message size), so no MSH fields can be extracted. MSH-3/4/5/6
        are left blank and a fresh MSH-10 is generated if one isn't already known.
        """
        ack = Message("ACK", validation_level=VALIDATION_LEVEL.TOLERANT)
        control_id = message_control_id or self.generate_message_control_id()

        ack.msh.msh_1 = Hl7Constants.FIELD_SEPARATOR
        ack.msh.msh_2 = Hl7Constants.ENCODING_CHARACTERS
        ack.msh.msh_7 = datetime.now().strftime("%Y%m%d%H%M%S")
        ack.msh.msh_9.message_code = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        ack.msh.msh_9.message_structure = Hl7Constants.ACK_MESSAGE_TYPE_FORMAT
        ack.msh.msh_10 = control_id
        ack.msh.msh_11 = Hl7Constants.PROCESSING_ID_PRODUCTION
        ack.msh.msh_12 = Hl7Constants.DEFAULT_HL7_VERSION

        msa = Segment("MSA", validation_level=VALIDATION_LEVEL.TOLERANT)
        msa.msa_1 = Hl7Constants.ACK_CODE_ERROR
        msa.msa_2 = control_id
        msa.msa_3 = self._sanitize_reason(reason)
        ack.add(msa)

        return ack

    @staticmethod
    def generate_message_control_id() -> str:
        """Generate a unique control ID no longer than 20 characters (MSH.10 limit)."""
        return uuid.uuid4().hex[: Hl7Constants.GENERATED_CONTROL_ID_MAX_LENGTH]

    @staticmethod
    def _sanitize_reason(reason: str) -> str:
        """Strip line breaks (which would corrupt HL7 segment framing) and cap length to keep the
        NACK consumable by downstream systems that parse MSA-3 strictly."""
        sanitized = reason.replace("\r", " ").replace("\n", " ")
        return sanitized[: Hl7Constants.MAX_NACK_REASON_LENGTH]
