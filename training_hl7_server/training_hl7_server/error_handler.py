"""
Fallback Error Handler (EXERCISE 2 SOLUTION)
=============================================

This module implements a fallback error handler that catches any message type
not explicitly registered in the handlers dictionary. This is a safety net
that ensures we always respond to the sender, even if we can't process their
message.

WHY DO WE NEED AN ERROR HANDLER?
--------------------------------
The MLLP server uses a handlers dictionary to route messages to the
appropriate handler based on the message type (MSH-9). For example:

    handlers = {
        "ADT^A31": (MessageHandler, ...),  # Specific handler for A31
        "ADT^A28": (MessageHandler, ...),  # Specific handler for A28
    }

But what happens if someone sends an ADT^A04 message that's not in our
handlers dictionary? Without an error handler, the MLLP library would
raise an UnsupportedMessageType exception and the connection might drop
without sending any response.

With an error handler registered under the "ERR" key, we can:
1. Catch any unhandled message type
2. Log the issue for troubleshooting
3. Return a proper NACK (negative acknowledgment) to the sender

PRODUCTION REFERENCE:
--------------------
See hl7_server/hl7_server/error_handler.py for the production implementation
which integrates with the EventLogger for audit logging.

USAGE IN HANDLERS DICTIONARY:
-----------------------------
The error handler is registered with the special key "ERR":

    handlers = {
        "ADT^A31": (MessageHandler, config.hl7_version),
        "ADT^A28": (MessageHandler, config.hl7_version),
        "ERR": (ErrorHandler,),  # Catches all other message types
    }
"""

from hl7apy.mllp import AbstractErrorHandler, UnsupportedMessageType
from hl7apy.parser import parse_message

from training_hl7_server.ack_builder import AckBuilder
from training_hl7_server.constants import Hl7Constants


class ErrorHandler(AbstractErrorHandler):
    """
    Fallback handler for unsupported or invalid messages.

    This handler is invoked when:
    1. A message type is received that's not in the handlers dictionary
    2. A message cannot be parsed or is malformed
    3. An exception occurs during message processing

    The MLLP library automatically passes information about the error to this
    handler, which we use to construct an appropriate error response.

    Inheritance Chain:
    -----------------
    AbstractErrorHandler -> Our ErrorHandler

    AbstractErrorHandler provides:
    - self.exc: The exception that was raised
    - self.incoming_message: The raw message string
    - Abstract reply() method that we must implement

    ACK Codes Explained:
    -------------------
    When returning an error ACK, we use one of these codes:
    - AE (Application Error): The message was received but validation failed
    - AR (Application Reject): The message couldn't be processed (system error)

    For unsupported message types, we return AE as it's a
    business logic issue - the message is well-formed but we don't
    handle that type.
    """

    def __init__(self, exc: Exception, incoming_message: str) -> None:
        """
        Initialize the error handler.

        This constructor is called automatically by the MLLP library when
        an error occurs. The library passes the exception and the original
        message so we can construct an appropriate response.

        Args:
            exc: The exception that was raised (e.g., UnsupportedMessageType).
            incoming_message: The raw HL7 message string that caused the error.
        """
        # Call the parent class constructor
        # AbstractErrorHandler expects these same arguments
        super().__init__(exc, incoming_message)

        # Create an AckBuilder to construct our error response
        self.ack_builder = AckBuilder()

    def reply(self) -> str:
        """
        Process the error and return an error ACK (NACK).

        This method is called by the MLLP library to get the response that
        should be sent back to the client. We analyze the exception type
        and construct an appropriate error response.

        Returns:
            An HL7 ACK message with an error code (AE or AR).

        Note:
            In production, errors are also logged to the event logging
            system for audit and troubleshooting. For this training example,
            we just print to console.
        """
        # =====================================================================
        # Log the error for troubleshooting
        # =====================================================================
        print("\n" + "=" * 60)
        print("ERROR HANDLER INVOKED")
        print("=" * 60)

        # =====================================================================
        # Determine the type of error
        # =====================================================================
        # UnsupportedMessageType is raised when a message type (MSH-9) is
        # received that doesn't have a registered handler

        if isinstance(self.exc, UnsupportedMessageType):
            # -------------------------------------------------------------
            # Handle unsupported message type
            # -------------------------------------------------------------
            error_message = f"Unsupported message type: {self.exc}"
            ack_code = Hl7Constants.ACK_CODE_ERROR  # AE - Application Error
            print(f"✗ {error_message}")
            print("  This message type is not configured in the handlers dictionary.")
            print("  To support this type, add it to the handlers dict in server_application.py")
        else:
            # -------------------------------------------------------------
            # Handle other errors (parsing errors, system errors, etc.)
            # -------------------------------------------------------------
            error_message = f"Error processing message: {self.exc}"
            ack_code = Hl7Constants.ACK_CODE_REJECT  # AR - Application Reject
            print(f"✗ {error_message}")

        print("=" * 60 + "\n")

        # =====================================================================
        # Try to build an error ACK
        # =====================================================================
        # We attempt to parse the message to get the control ID and other
        # fields needed for the ACK. If parsing fails, we have to re-raise
        # the exception since we can't construct a valid ACK.

        try:
            # Try to parse enough of the message to build an ACK
            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value

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
            # -----------------------------------------------------------------
            # If we can't even parse the message, we can't build an ACK
            # -----------------------------------------------------------------
            # In this case, we re-raise the original exception which will
            # cause the MLLP library to close the connection. The sender
            # will know something went wrong when they don't receive a response.
            print(f"✗ Cannot parse message to build ACK: {parse_error}")
            print("  Re-raising original exception")
            raise self.exc