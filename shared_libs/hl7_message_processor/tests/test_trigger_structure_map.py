import unittest

from hl7_message_processor.trigger_structure_map import (
    STRUCTURE_TRIGGERS,
    TRIGGER_TO_STRUCTURE,
    resolve_structure_from_trigger,
)


class TriggerStructureMapTests(unittest.TestCase):
    def test_a28_resolves_to_adt_a05(self) -> None:
        self.assertEqual(resolve_structure_from_trigger("ADT", "A28"), "ADT_A05")

    def test_a40_resolves_to_adt_a39(self) -> None:
        self.assertEqual(resolve_structure_from_trigger("ADT", "A40"), "ADT_A39")

    def test_strips_whitespace(self) -> None:
        self.assertEqual(resolve_structure_from_trigger(" ADT ", " A40 "), "ADT_A39")

    def test_unknown_pair_returns_none(self) -> None:
        self.assertIsNone(resolve_structure_from_trigger("ZZZ", "Z99"))

    def test_corrected_brp_o30_entry_present(self) -> None:
        self.assertIn("BRP_O30", STRUCTURE_TRIGGERS)
        self.assertNotIn("BRP_030", STRUCTURE_TRIGGERS)
        self.assertEqual(resolve_structure_from_trigger("BRP", "O30"), "BRP_O30")

    def test_corrected_orr_o02_entry_present(self) -> None:
        self.assertIn("ORR_O02", STRUCTURE_TRIGGERS)
        self.assertNotIn("ORR_R02", STRUCTURE_TRIGGERS)
        self.assertEqual(resolve_structure_from_trigger("ORR", "O02"), "ORR_O02")

    def test_no_silent_collisions_in_reverse_index(self) -> None:
        """Every (message_code, trigger) pair should map to exactly one structure.

        Rebuilds the expected index directly from STRUCTURE_TRIGGERS (first-occurrence-wins) and
        checks it against the module's own TRIGGER_TO_STRUCTURE, so a future edit introducing a
        genuine collision changes behaviour visibly instead of failing silently.
        """
        seen: dict[tuple[str, str], str] = {}
        collisions = []
        for structure, triggers in STRUCTURE_TRIGGERS.items():
            message_code = structure.split("_", 1)[0]
            for trigger in triggers:
                key = (message_code, trigger)
                if key in seen and seen[key] != structure:
                    collisions.append((key, seen[key], structure))
                else:
                    seen.setdefault(key, structure)
        self.assertEqual(collisions, [], f"Unexpected (message_code, trigger) collisions: {collisions}")
        self.assertEqual(TRIGGER_TO_STRUCTURE, seen)


if __name__ == "__main__":
    unittest.main()
