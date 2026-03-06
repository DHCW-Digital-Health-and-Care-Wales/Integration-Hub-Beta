from hl7apy.core import Message
from copy import deepcopy


def find_segments(element, segment_name):
    """Recursively find segments in an HL7apy message."""
    segments = []

    for child in element.children:
        if child.name == segment_name:
            segments.append(child)

        # Recurse into groups
        if hasattr(child, "children"):
            segments.extend(find_segments(child, segment_name))

    return segments


def map_obx(original_message: Message, new_message: Message) -> None:
    print("Mapping OBX segments...")

    obx_segments = find_segments(original_message, "OBX")

    print(f"Found {len(obx_segments)} OBX segments")

    for obx in obx_segments:

        new_obx = deepcopy(obx)

        try:
            if new_obx.obx_2.value == "ED":

                for rep in new_obx.obx_5:

                    if hasattr(rep, "ed_5"):
                        data = rep.ed_5.value

                        if data and data.startswith("JVBERi"):
                            print("PDF detected → replacing with pdffile.txt")
                            rep.ed_5.value = "pdffile.txt"

        except Exception as e:
            print(f"OBX processing warning: {e}")

        new_message.add(new_obx)