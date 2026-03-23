from hl7apy.core import Message
from copy import deepcopy


def find_segments(element, segment_name):
    """Recursively find segments in an HL7apy message."""
    segments = []

    for child in element.children:
        print(f"Checking child: {child.name} of type {type(child).__name__}")
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
        try:
            # Create a new OBX segment in the new message
            new_obx = new_message.add_segment("OBX")

            # Copy fields from the original OBX segment to the new one
            for field in obx.children:
                new_obx.add(field)

            # Check if OBX-2 is "ED" and process OBX-5
            if new_obx.obx_2.value == "ED":
                print("Processing OBX segment with ED data type...")
                for rep in new_obx.obx_5:
                    # Access OBX.5.5 (5th component of OBX-5)
                    if hasattr(rep, "children") and len(rep.children) >= 5:
                        obx_5_5 = rep.children[4].value  # OBX.5.5 is the 5th component (index 4)
                        print(f"OBX.5.5 value: {obx_5_5}")
                        if obx_5_5 and obx_5_5.startswith("JVBERi"):
                            print("PDF detected → replacing with pdffile.txt")
                            rep.children[4].value = "pdffile.txt"  # Replace OBX.5.5 value

        except Exception as e:
            print(f"OBX processing warning: {e}")

        new_message.add(new_obx)