from hl7apy.core import Message


def map_non_specific_segments(original_msg: Message, new_msg: Message) -> None:

    handled_segments = {"MSH", "PID"}

    for segment in original_msg.children:
        segment_name = segment.name
        if segment_name not in handled_segments:
            new_segment = new_msg.add_segment(segment_name)
            processed_fields: set[str] = set()
            for field in segment.children:
                field_name = field.name.lower()
                if field_name in processed_fields:
                    continue
                processed_fields.add(field_name)

                source_field = getattr(segment, field_name, None)
                if source_field is None:
                    continue

                try:
                    repetitions = len(source_field)  # type: ignore[arg-type]
                except (TypeError, AttributeError):
                    if field.value:
                        getattr(new_segment, field_name).value = field.value
                    continue

                for i in range(repetitions):
                    new_rep = new_segment.add_field(field_name)
                    new_rep.value = source_field[i].value

