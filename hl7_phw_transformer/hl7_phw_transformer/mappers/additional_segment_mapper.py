from hl7apy.core import Message


def map_non_specific_segments(original_msg: Message, new_msg: Message) -> None:

    handled_segments = {"MSH", "PID"}

    for segment in original_msg.children:
        segment_name = segment.name
        if segment_name not in handled_segments:
            new_segment = new_msg.add_segment(segment_name)
            for field in segment.children:
                field_name = field.name
                if field.value:
                    getattr(new_segment, field_name.lower()).value = field.value

