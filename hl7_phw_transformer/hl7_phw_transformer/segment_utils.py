from typing import Any


def copy_segment_fields_with_repetitions(
    source_segment: Any,
    target_segment: Any,
    field_prefix: str,
    start: int,
    end: int,
) -> None:
    """
    Copy fields from source_segment to target_segment, preserving all repetitions.

    This is similar in spirit to copy_segment_fields_in_range from field_utils_lib,
    but ensures that any repeating fields are copied rep-by-rep rather than
    losing additional repetitions.
    """
    for index in range(start, end + 1):
        field_name = f"{field_prefix}_{index}"
        try:
            source_field = getattr(source_segment, field_name)
        except Exception:
            # Some HL7 libraries raise custom exceptions instead of AttributeError
            # when a field does not exist; in those cases we just skip the field.
            continue

        try:
            repetitions = len(source_field)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            value = source_field.value
            if value:
                getattr(target_segment, field_name).value = value
            continue

        # Repeating field: copy each repetition. For the first repetition, if
        # the target already has a default empty repetition, reuse it instead
        # of appending a new one, to avoid leading empty repetitions. For all
        # others, append new repetitions.
        target_field = getattr(target_segment, field_name)
        try:
            target_reps = len(target_field)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            target_reps = 0

        for i in range(repetitions):
            value = source_field[i].value
            if i == 0 and target_reps > 0:
                try:
                    first_rep = target_field[0]
                except Exception:
                    first_rep = target_segment.add_field(field_name)
                first_rep.value = value
            else:
                new_rep = target_segment.add_field(field_name)
                new_rep.value = value

