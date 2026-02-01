"""ACK message builder for HL7 responses."""

from datetime import datetime

from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.core import Message, Segment

from training_hl7_server.constants import Hl7Constants


class AckBuilder:
    """Builds HL7 ACK messages in response to incoming messages."""

    def build_ack(
        self,
        message_control_id: str,
        original_msg: Message,
        ack_code: str = Hl7Constants.ACK_CODE_ACCEPT,
        error_message: str | None = None,
    ) -> Message:
        """
        Build an ACK message based on the original message.

        An ACK (acknowledgment) is sent back to the sender to confirm receipt
        and indicate whether the message was successfully processed.

        Args:
            message_control_id: The control ID from the original message (MSH-10).
                               This uniquely identifies the message being acknowledged.
            original_msg: The parsed original HL7 message.
            ack_code: The acknowledgment code (AA=Accept, AE=Error).
            error_message: Optional error message text for AE responses.

        Returns:
            A constructed ACK message ready to be sent.
        """

        print(f"\n✓ Building ACK message with ACK code: '{ack_code}'")

        # Create a new ACK message using hl7apy
        # VALIDATION_LEVEL.STRICT ensures the message follows HL7 standards
        ack = Message("ACK", validation_level=VALIDATION_LEVEL.STRICT)

        # ===================================================================
        # Build MSH (Message Header) segment
        # ===================================================================
        # The MSH segment identifies the sender, receiver, message type, etc.

        # MSH-1: Field Separator (always "|")
        ack.msh.msh_1 = Hl7Constants.FIELD_SEPARATOR

        # MSH-2: Encoding Characters (always "^~\&")
        ack.msh.msh_2 = Hl7Constants.ENCODING_CHARACTERS

        # MSH-3: Sending Application
        # In an ACK, we SWAP sender and receiver from the original message
        # The original receiver becomes the sender of the ACK
        ack.msh.msh_3 = original_msg.msh.msh_5.value  # Receiving app becomes sending

        # MSH-4: Sending Facility
        ack.msh.msh_4 = original_msg.msh.msh_6.value  # Receiving facility becomes sending

        # MSH-5: Receiving Application
        # The original sender becomes the receiver of the ACK
        ack.msh.msh_5 = original_msg.msh.msh_3.value  # Sending app becomes receiving

        # MSH-6: Receiving Facility
        ack.msh.msh_6 = original_msg.msh.msh_4.value  # Sending facility becomes receiving

        # MSH-7: Timestamp - when this ACK was created
        # Format: YYYYMMDDHHMMSS
        ack.msh.msh_7 = datetime.now().strftime("%Y%m%d%H%M%S")

        # MSH-9: Message Type
        # For ACK messages, we keep the trigger event from the original message
        # Example: If original was ADT^A31, ACK will be ACK^A31
        ack.msh.msh_9.message_code = Hl7Constants.ACK_MESSAGE_TYPE
        ack.msh.msh_9.trigger_event = original_msg.msh.msh_9.trigger_event.value

        # MSH-10: Message Control ID - same as the original message
        # This links the ACK to the specific message it's acknowledging
        ack.msh.msh_10 = message_control_id

        # MSH-11: Processing ID (P=Production, T=Training, D=Debugging)
        ack.msh.msh_11 = Hl7Constants.PROCESSING_ID_PRODUCTION

        # MSH-12: Version ID - must match the original message version
        ack.msh.msh_12 = original_msg.msh.msh_12.value  # pyright: ignore[reportOptionalMemberAccess]

        # ===================================================================
        # Build MSA (Message Acknowledgment) segment
        # ===================================================================
        # The MSA segment contains the acknowledgment code and any error details

        msa = Segment("MSA", validation_level=VALIDATION_LEVEL.STRICT)

        # MSA-1: Acknowledgment Code
        # AA = Application Accept (success)
        # AE = Application Error (validation failed)
        # AR = Application Reject (system error)
        msa.msa_1 = ack_code

        # MSA-2: Message Control ID - same as MSH-10
        # This confirms which message is being acknowledged
        msa.msa_2 = message_control_id

        # MSA-3: Text Message (optional)
        # Include error details if this is an error acknowledgment
        if error_message:
            msa.msa_3 = error_message

        # Add the MSA segment to the ACK message
        ack.add(msa)

        return ack
