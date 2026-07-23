from hl7apy.core import Message


def _is_a04_or_a08_trigger_event(original_msg: Message) -> bool:
    try:
        return original_msg.msh.msh_9.msg_2.value in {"A04", "A08"}
    except AttributeError:
        return False


def _map_pd1(original_segment: object, new_msg: Message, copy_values: bool) -> None:
    new_pd1 = new_msg.add_segment("PD1")
    if not copy_values:
        return

    original_pd1_4 = getattr(original_segment, "pd1_4", [])
    if len(original_pd1_4) > 0:
        new_pd1.pd1_4.xcn_1 = original_pd1_4[0].xcn_1.value
    if len(original_pd1_4) > 1:
        new_pd1.pd1_3.xon_3 = original_pd1_4[1].xcn_1.value


def _map_pv1(new_msg: Message, copy_values: bool) -> None:
    new_pv1 = new_msg.add_segment("PV1")
    if copy_values:
        new_pv1.pv1_2.value = "N"


def _map_mrg(original_segment: object, new_msg: Message, copy_values: bool) -> None:
    new_mrg = new_msg.add_segment("MRG")
    if not copy_values:
        return

    new_mrg.mrg_1.cx_1 = original_segment.mrg_1.cx_1.value
    new_mrg.mrg_1.cx_4.hd_1 = "103"
    new_mrg.mrg_1.cx_5 = "PI"


def map_non_specific_segments(original_msg: Message, new_msg: Message) -> None:

    handled_segments = {"MSH", "EVN", "PID"}
    trigger_event = getattr(original_msg.msh.msh_9.msg_2, "value", "")
    is_a04_or_a08 = _is_a04_or_a08_trigger_event(original_msg)
    is_a40 = trigger_event == "A40"

    for segment in original_msg.children:
        segment_name = segment.name
        if segment_name not in handled_segments:
            if segment_name == "PD1":
                _map_pd1(segment, new_msg, is_a04_or_a08)
                continue
            if segment_name == "PV1":
                _map_pv1(new_msg, is_a04_or_a08)
                continue
            if segment_name == "MRG":
                _map_mrg(segment, new_msg, is_a40)
                continue

            new_segment = new_msg.add_segment(segment_name)
            for field in segment.children:
                field_name = field.name.lower()
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

