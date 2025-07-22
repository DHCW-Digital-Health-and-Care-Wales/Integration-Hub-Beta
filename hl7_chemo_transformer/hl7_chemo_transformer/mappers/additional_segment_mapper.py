from hl7apy.core import Message


def map_non_specific_segments(original_hl7_message: Message, new_message: Message) -> None:
    """
    Maps non-specific segments which have not been explicity specified by the business rules
    from the original message to the new message, with no special transformation logic.
    """
    segments = ["pv1", "pv2", "obx", "al1", "dg1", "pr1", "gt1", "in1", "in2", "in3"]

    for segment in segments:
        try:
            if hasattr(original_hl7_message, segment):
                segment_value = getattr(original_hl7_message, segment)
                if segment_value:
                    setattr(new_message, segment, segment_value)
        except (AttributeError, TypeError) as e:
            # A failure with one of these segments should not stop the entire mapping
            # as the required field mapping has already been completed
            print("Error copying segment {}: {}".format(segment, str(e)))
