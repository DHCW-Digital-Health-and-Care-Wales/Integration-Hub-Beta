from hl7apy.core import Message, Segment

class AckBuilder: 
    def build_ack(self, 
                  message_control_id, 
                  original_msg,
                  ack_code,
                  error_message: str | None = None
    ) -> Message: