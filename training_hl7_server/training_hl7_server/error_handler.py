

from hl7apy.mllp import AbstractErrorHandler, UnsupportedMessageType
from hl7apy.parser import parse_message

from training_hl7_server.ack_builder import AckBuilder
from training_hl7_server.constants import HL7Constants


class ErrorHandler(AbstractErrorHandler):
    def __init__(self, exc: Exception, msg: str):
        super().__init__(exc, msg)

    def reply(self) -> str: # type: ignore
        # Dummy Log the error for troubleshooting
        print("\n" + "=" * 60)
        print("ERROR HANDLER INVOKED")
        print("=" * 60)
        if isinstance(self.exc, UnsupportedMessageType):
            error_msg = str(self.exc)
            error_msg = error_msg.replace("^", " ")  # ^ is the default component separator in HL7
            print(error_msg)
        else:
            error_msg = f"Invalid HL7 Message: {self.exc}"
            print(error_msg)

        try:
            # Create an instance of AckBuilder to construct ACK responses
            self.ack_builder = AckBuilder()
            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value


            # Build an AE (Application Error) ACK with error details
            ack = self.ack_builder.build_ack(
                message_control_id=message_control_id,
                original_msg=msg,
                ack_code=HL7Constants.ACK_CODE_ERROR,
                error_message= error_msg,
            )
            return ack.to_er7()
        except Exception as e:
            # If we can't even parse the message, re-raise the original error
            print(f"Failed to parse message for error ACK: {e}")

            raise self.exc
