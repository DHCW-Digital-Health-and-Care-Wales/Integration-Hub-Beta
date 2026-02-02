"""Message handler for processing incoming HL7 messages."""

from typing import Optional

from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message

# WEEK 2 ADDITION: Import MessageSenderClient for type hints
from message_bus_lib.message_sender_client import MessageSenderClient

from training_hl7_server.ack_builder import AckBuilder
from training_hl7_server.constants import Hl7Constants


class ValidationError(Exception):
    """
    Raised when HL7 message validation fails.

    This custom exception is used to distinguish validation errors from
    other types of errors. When we catch this exception, we know the
    message was well-formed but failed our business rules.

    Examples of validation errors:
    - Wrong HL7 version in MSH-12
    - Sending application not in allowed list
    - Missing required fields
    """

    pass


class MessageHandler(AbstractHandler):
    """
    Handler for processing incoming HL7 messages.

    This handler:
    1. Parses the incoming HL7 message
    2. Validates the HL7 version (MSH-12)
    3. Validates the sending application (MSH-3) - EXERCISE 4 SOLUTION
    4. Prints message contents for debugging
    5. Returns an ACK response

    Inherits from AbstractHandler which is part of the hl7apy MLLP framework.
    The reply() method is called automatically when a message is received.

    EXERCISE 4 SOLUTION - Allowed Senders Validation:
    ------------------------------------------------
    This handler now validates that the sending application (MSH-3) is in
    an allowed list configured via environment variable. This mirrors the
    production server's SENDING_APP validation in hl7_validator.py.

    Why validate sending applications?
    1. Security: Only accept messages from known, trusted systems
    2. Data integrity: Ensure messages come from expected sources
    3. Debugging: Quickly identify rogue systems sending to wrong endpoint
    """

    def __init__(
        self,
        incoming_message: str,
        expected_version: Optional[str] = None,
        allowed_senders: Optional[str] = None,
        sender_client: Optional[MessageSenderClient] = None,
    ) -> None:
        """
        Initialize the message handler.

        Args:
            incoming_message: The raw HL7 message string.
            expected_version: The expected HL7 version in MSH-12.
                              If None, version validation is skipped.
            allowed_senders: Comma-separated list of allowed sending app codes.
                             If None, all senders are accepted.
                             Example: "169,245" allows only apps 169 and 245.
            sender_client: WEEK 2 ADDITION - Service Bus sender client.
                           If provided, validated messages are published to the queue.
                           If None, messages are only processed locally (Week 1 mode).
        """
        # Call parent class constructor to set up the handler
        super().__init__(incoming_message)

        # Store the expected HL7 version for validation (can be None to skip)
        self.expected_version: Optional[str] = expected_version

        # =====================================================================
        # EXERCISE 4: Store allowed senders list
        # =====================================================================
        # Parse the comma-separated string into a list of allowed sender codes.
        # If allowed_senders is None or empty, we accept all senders.
        #
        # Production Reference:
        # See hl7_server/hl7_server/hl7_validator.py _validate_sending_app()
        # which implements this same pattern.
        if allowed_senders:
            # Split by comma and strip whitespace from each item
            # "169, 245" becomes ["169", "245"]
            self.allowed_senders: Optional[list[str]] = [app.strip() for app in allowed_senders.split(",")]
        else:
            # If no allowed senders configured, set to None (accept all)
            self.allowed_senders = None

        # =====================================================================
        # WEEK 2 ADDITION: Store the Service Bus sender client
        # =====================================================================
        # If configured, this client will be used to publish validated messages
        # to Azure Service Bus for the transformer to process.
        self.sender_client = sender_client

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
            message_control_id = msg.msh.msh_10.value

            # MSH-9: Message Type - format is "MessageType^TriggerEvent"
            # Example: "ADT^A31" means ADT message with trigger event A31
            message_type = msg.msh.msh_9.to_er7()

            # MSH-12: Version ID - the HL7 version (e.g., "2.3.1")
            hl7_version = msg.msh.msh_12.value

            # MSH-3: Sending Application - the system that sent this message
            sending_app = msg.msh.msh_3.value

            # MSH-4: Sending Facility - the facility/hospital that sent the message
            sending_facility = msg.msh.msh_4.value

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
            # STEP 4: Validate the message
            # ===================================================================
            # Run all validation checks. If any fail, a ValidationError is raised
            # and we return an error ACK (AE) to the sender.

            # 4a. Validate HL7 version (original validation)
            self._validate_version(hl7_version)

            # 4b. EXERCISE 4 SOLUTION: Validate sending application
            self._validate_sending_app(sending_app)

            # ===================================================================
            # STEP 5: Publish to Service Bus (WEEK 2 ADDITION)
            # ===================================================================
            # If Service Bus is configured, publish the validated message to
            # the egress queue. The transformer component will pick it up.
            if self.sender_client:
                print("-" * 60)
                print("PUBLISHING TO SERVICE BUS (Week 2)")
                # Publish the raw HL7 message as UTF-8 text
                # The transformer will parse and transform this message
                self.sender_client.send_text_message(self.incoming_message)
                print(f"✓ Message published to egress queue: {message_control_id}")
            else:
                print("  (Service Bus publishing skipped - sender not configured)")

            # ===================================================================
            # STEP 6: Build and return a success ACK
            # ===================================================================
            # If we got here, validation passed - send an AA (Application Accept) ACK
            ack = self.ack_builder.build_ack(
                message_control_id=message_control_id,
                original_msg=msg,
                ack_code=Hl7Constants.ACK_CODE_ACCEPT,
            )
            print(f"✓ Sending ACK (AA) for message {message_control_id}")

            # Convert the ACK Message object to MLLP format (ER7 with framing bytes)
            # MLLP requires start byte (\x0b) and end bytes (\x1c\x0d)
            return ack.to_mllp()

        except ValidationError as e:
            # ===================================================================
            # Handle validation errors (e.g., wrong HL7 version)
            # ===================================================================
            print(f"✗ Validation Error: {e}")

            # Try to build an error ACK if we can parse enough of the message
            try:
                msg = parse_message(self.incoming_message, find_groups=False)
                message_control_id = msg.msh.msh_10.value

                # Build an AE (Application Error) ACK with error details
                ack = self.ack_builder.build_ack(
                    message_control_id=message_control_id,
                    original_msg=msg,
                    ack_code=Hl7Constants.ACK_CODE_ERROR,
                    error_message=str(e),
                )
                return ack.to_mllp()
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
        # Skip validation if no expected version is configured
        # This allows the server to accept any HL7 version when HL7_VERSION is not set
        if self.expected_version is None:
            print("  (HL7 version validation skipped - no version configured)")
            return

        if message_version != self.expected_version:
            raise ValidationError(f"Invalid HL7 version: expected '{self.expected_version}', got '{message_version}'")
        print(f"✓ HL7 version validated: {message_version}")

    def _validate_sending_app(self, sending_app: str) -> None:
        """
        Validate the sending application from MSH-3 (EXERCISE 4 SOLUTION).

        This ensures we only accept messages from authorized systems. In
        healthcare integration, it's crucial to know exactly which systems
        are sending data and to reject messages from unknown sources.

        Production Reference:
        --------------------
        See hl7_server/hl7_server/hl7_validator.py _validate_sending_app()
        which implements this same pattern. In production, the allowed
        senders are configured via the SENDING_APP environment variable.

        Why validate sending applications?
        ---------------------------------
        1. SECURITY: Prevent unauthorized systems from injecting data
        2. DATA INTEGRITY: Ensure data comes from known, trusted sources
        3. DEBUGGING: Quickly identify misconfigured systems
        4. COMPLIANCE: Healthcare regulations often require message tracing

        Configuration:
        -------------
        Set ALLOWED_SENDERS="169,245" in the environment to only accept
        messages from sending applications 169 and 245.

        Args:
            sending_app: The sending application code from MSH-3.

        Raises:
            ValidationError: If the sending app is not in the allowed list.

        Example:
            # Message with MSH-3 = "169" when ALLOWED_SENDERS="169,245"
            # -> Validation passes

            # Message with MSH-3 = "999" when ALLOWED_SENDERS="169,245"
            # -> ValidationError raised, AE ACK returned
        """
        # Skip validation if no allowed senders list is configured
        # This is the "open" mode where any sender is accepted
        if self.allowed_senders is None:
            print("(Sending app validation skipped - no allowed list configured)")
            return

        # Check if the sending app is in our allowed list
        if sending_app not in self.allowed_senders:
            # Build a helpful error message that includes the allowed apps
            allowed_list = ", ".join(self.allowed_senders)
            raise ValidationError(f"Sending application '{sending_app}' is not in allowed list: [{allowed_list}]")

        print(f"Sending application validated: {sending_app} (in allowed list)")
