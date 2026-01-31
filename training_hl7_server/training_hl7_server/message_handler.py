"""Message handler for processing incoming HL7 messages."""

from hl7apy.mllp import AbstractHandler  # type: ignore[import-untyped]
from hl7apy.parser import parse_message  # type: ignore[import-untyped]

from training_hl7_server.ack_builder import AckBuilder
from training_hl7_server.constants import Hl7Constants


class ValidationError(Exception):
    """Raised when HL7 message validation fails."""
    pass


class MessageHandler(AbstractHandler):
    """
    Handler for processing incoming HL7 messages.

    This handler:
    1. Parses the incoming HL7 message
    2. Validates the HL7 version (MSH-12)
    3. Prints message contents for debugging
    4. Returns an ACK response

    Inherits from AbstractHandler which is part of the hl7apy MLLP framework.
    The reply() method is called automatically when a message is received.
    """

    def __init__(
        self,
        incoming_message: str,
        expected_version: str | None = None,
        allowed_senders: str | None = None,
    ) -> None:
        """
        Initialize the message handler.

        Args:
            incoming_message: The raw HL7 message string.
            expected_version: The expected HL7 version in MSH-12. If None ver validation is skipped.
            allowed_senders: Comma-separated list of allowed sending applications/facilities.
            If None, all senders accepted. e.g. "169,125"
        """
        # Call parent class constructor to set up the handler
        super().__init__(incoming_message)

        # Store the expected HL7 version for validation
        self.expected_version = expected_version

        self.allowed_senders = allowed_senders

          # Create an instance of AckBuilder to construct ACK responses
        self.ack_builder = AckBuilder()

    def reply(self) -> str:
        """
        Process the incoming message and return an ACK response.

        This method is called automatically by the MLLP server when a message
        is received. It must return a string containing the ACK message.

        Returns:
            The HL7 ACK message as a string.
        """
        # Print a header to make the console output easier to read
        print("\n" + "=" * 60)
        print("RECEIVED HL7 MESSAGE")
        print("=" * 60)

        try:
            # ===================================================================
            # STEP 1: Parse the incoming message
            # ===================================================================
            # parse_message() converts the raw HL7 string into a structured
            # Message object that we can easily work with
            # find_groups=False disables group parsing for simplicity
            msg = parse_message(self.incoming_message, find_groups=False)

            # ===================================================================
            # STEP 2: Extract key fields from the MSH segment
            # ===================================================================
            # The MSH (Message Header) segment contains metadata about the message

            # MSH-10: Message Control ID - unique identifier for this message
            message_control_id = msg.msh.msh_10.value # type: ignore

            # MSH-9: Message Type - format is "MessageType^TriggerEvent"
            # Example: "ADT^A31" means ADT message with trigger event A31
            message_type = msg.msh.msh_9.to_er7() # type: ignore

            # MSH-12: Version ID - the HL7 version (e.g., "2.3.1")
            hl7_version = msg.msh.msh_12.value # type: ignore

            # MSH-3: Sending Application - the system that sent this message
            sending_app = msg.msh.msh_3.value # type: ignore

            # MSH-4: Sending Facility - the facility/hospital that sent the message
            sending_facility = msg.msh.msh_4.value # type: ignore

            # ===================================================================
            # STEP 3: Print message details for debugging
            # ===================================================================
            print(f"Message Type: {message_type}")
            print(f"Control ID: {message_control_id}")
            print(f"HL7 Version: {hl7_version}")
            print(f"Sending App: {sending_app}")
            print(f"Sending Facility: {sending_facility}")
            print("-" * 60)
            print("Raw Message:")
            print(self.incoming_message)
            print("=" * 60 + "\n")

            # ===================================================================
            # STEP 4: Validate the HL7 version
            # ===================================================================
            # 4a: Ensure the message uses the expected HL7 version
            self._validate_version(hl7_version)
            # ===================================================================
            # STEP 4: Validate the senders
            # ===================================================================
            # 4b: Ensure the sending application is in the allowed list
            self._validate_sending_app(sending_app)

            # ===================================================================
            # STEP 5: Build and return a success ACK
            # ===================================================================
            # If we got here, validation passed - send an AA (Application Accept) ACK
            ack = self.ack_builder.build_ack(
                message_control_id=message_control_id,
                original_msg=msg,
                ack_code=Hl7Constants.ACK_CODE_ACCEPT,
            )
            print(f"✓ Sending ACK (AA) for message {message_control_id}")

            # Convert the ACK Message object to ER7 format (pipe-delimited string)
            return ack.to_er7()

        except ValidationError as e:
            # ===================================================================
            # Handle validation errors (e.g., wrong HL7 version)
            # ===================================================================
            print(f"✗ Validation Error: {e}")

            # Try to build an error ACK if we can parse enough of the message
            try:
                msg = parse_message(self.incoming_message, find_groups=False)
                message_control_id = msg.msh.msh_10.value # type: ignore

                # Build an AE (Application Error) ACK with error details
                ack = self.ack_builder.build_ack(
                    message_control_id=message_control_id,
                    original_msg=msg,
                    ack_code=Hl7Constants.ACK_CODE_ERROR,
                    error_message=str(e),
                )
                return ack.to_er7()
            except Exception:
                # If we can't even parse the message, re-raise the original error
                raise

        except Exception as e:
            # ===================================================================
            # Handle unexpected errors (e.g., malformed messages)
            # ===================================================================
            print(f"✗ Error processing message: {e}")
            raise

    def _validate_version(self, message_version: str) -> None:
        """
        Validate the HL7 version from MSH-12.

        This ensures we only accept messages with the expected HL7 version.
        Different HL7 versions can have different field definitions and
        requirements, so it's important to validate this.

        Args:
            message_version: The HL7 version from the message.

        Raises:
            ValidationError: If the version doesn't match expected.
        """
        if self.expected_version is None:
            print("✓ HL7 version validation skipped")
            return

        if message_version != self.expected_version:
            raise ValidationError(f"Invalid HL7 version: expected '{self.expected_version}', got '{message_version}'")
        print(f"✓ HL7 version validated: {message_version}")

    def _validate_sending_app(self, sending_app: str) -> None:
        """
        Validate the sending application against allowed senders list.
        Args:
            sending_app: The sending application from MSH-3.
        Raises:
            ValidationError: If the sending application is not in the allowed list.
        """
        # If no allowed_senders configured, skip validation
        if self.allowed_senders is None:
            print("✖ Sending application validation skipped - no allowed_senders configured")
            return

        # Parse comma-separated list of allowed senders and strip whitespace
        senders = [app.strip() for app in self.allowed_senders.split(",")]

        # Validate that the sending application is in the allowed list
        if sending_app and sending_app not in senders:
            print("✖ Sending application validation failed - not in allowed_senders")
            raise ValidationError(f"Sending application '{sending_app}' is not in the allowed senders {senders}.")

        print(f"✓ Sending application validated: {sending_app}")
