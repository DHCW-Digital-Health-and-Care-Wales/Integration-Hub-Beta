from hl7apy.mllp import AbstractErrorHandler, UnsupportedMessageType  # type: ignore
from hl7apy.parser import parse_message  # type: ignore

from training_hl7_server.constants import Hl7Constants

from .ack_builder import AckBuilder


class ErrorHandler(AbstractErrorHandler):
    """Fallback error handler for unsupported message types and processing errors."""
    def __init__(self, exc: Exception, incoming_message: str) -> None:

        # Call the parent class constructor
        # AbstractErrorHandler expects these same arguments
        super().__init__(exc, incoming_message)
        # Create an AckBuilder to construct our error response
        self.ack_builder = AckBuilder()

    def reply(self) -> str: # type: ignore

        # Dummy Log the error for troubleshooting
        print("\n" + "=" * 60)
        print("ERROR HANDLER INVOKED")
        print("=" * 60)

        # Determine the type of error
        # UnsupportedMessageType is raised when a message type (MSH-9) is
        # received that doesn't have a registered handler

        if isinstance(self.exc, UnsupportedMessageType):
            # Handle unsupported message type
            error_message = f"Unsupported message type: {self.exc}"
            ack_code = Hl7Constants.ACK_CODE_ERROR  # AE - Application Error
            print(f"✗ {error_message}")
            print("  This message type is not configured in the handlers dictionary.")
            print("  To support this type, add it to the handlers dict in server_application.py")
        else:
            # Handle other errors (parsing errors, system errors, etc.)
            error_message = f"Error processing message: {self.exc}"
            ack_code = Hl7Constants.ACK_CODE_REJECT  # AR - Application Reject
            print(f"✗ {error_message}")

        print("=" * 60 + "\n")

        # Try to build an error ACK
        # We attempt to parse the message to get the control ID and other
        # fields needed for the ACK. If parsing fails, we have to re-raise
        # the exception since we can't construct a valid ACK.

        try:
            # Try to parse enough of the message to build an ACK
            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value # type: ignore

            # Build the error ACK
            ack = self.ack_builder.build_ack(
                message_control_id=message_control_id,
                original_msg=msg,
                ack_code=ack_code,
                error_message=error_message,
            )
            print(f"✓ Sending NACK ({ack_code}) for message {message_control_id}")
            return ack.to_er7()

        except Exception as parse_error:
        # If we can't even parse the message, we can't build an ACK. In this case, we re-raise the original exception
        # which will cause the MLLP library to close the connection. The sender will know something went wrong when
        # they don't receive a response.
            print(f"✗ Cannot parse message to build ACK: {parse_error}")
            print("  Re-raising original exception")
            raise self.exc
