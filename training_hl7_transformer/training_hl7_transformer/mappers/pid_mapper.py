from field_utils_lib import copy_segment_fields_in_range
from field_utils_lib.field_utils import get_hl7_field_value
from hl7apy.core import Message  # type: ignore[import-untyped]


def map_pid(original_message: Message, new_message: Message) -> dict[str, str] | None:
    """PID segment mapper function. Sets all lowercase to uppercase."""

    output_dict: dict[str, str] = {}

    print("=" * 60 + "\nMapping PID segment...\n" + "=" * 60)

    segment_names: list[str] = (
        [seg.name for seg in original_message.children] if original_message.children is not None else []
    )

    if "PID" not in segment_names:
        return None

    original_pid = original_message.pid
    new_pid = new_message.pid

    copy_segment_fields_in_range(
        source_segment=original_pid,
        target_segment=new_pid,
        field_prefix="pid",
        start=1,
        end=39,
    )

    try:
        new_pid.pid_5.xpn_1.fn_1.value = str(get_hl7_field_value(original_pid, "pid_5.xpn_1.fn_1")).upper()  # type: ignore
        output_dict["pid_5.xpn_1.fn_1"] = new_pid.pid_5.xpn_1.fn_1.value.upper()  # type: ignore
    except AttributeError:
        new_pid.pid_5.xpn_1.value = str(get_hl7_field_value(original_pid, "pid_5.xpn_1")).upper()  # type: ignore
        output_dict["pid_5.xpn_1.fn_1"] = new_pid.pid_5.xpn_1.value.upper()  # type: ignore

    xpn_fields = ["xpn_2", "xpn_3", "xpn_4", "xpn_5"]  # Given name, second name, suffix, prefix

    for xpn in xpn_fields:
        field_path = f"pid_5.{xpn}"
        try:
            value = get_hl7_field_value(original_pid, field_path).upper()
            getattr(new_pid.pid_5, xpn).value = value  # type: ignore
            output_dict[field_path] = value  # type: ignore
        except AttributeError:
            print(f"Field {field_path} not found in original PID segment. Setting to None.")
        except Exception as e:
            print(f"Unexpected error processing field {field_path}: {e}")

    if output_dict:
        return output_dict
    return None
