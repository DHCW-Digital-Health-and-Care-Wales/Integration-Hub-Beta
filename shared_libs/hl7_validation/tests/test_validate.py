import os
import unittest

from hl7_validation.validate import (
    _extract_trigger_event_from_er7,
)
from hl7_validation import get_schema_xsd_path_for


class TestSchemaPathResolutionAndTriggerParsing(unittest.TestCase):
    def test_get_schema_xsd_path_for(self) -> None:

        path = get_schema_xsd_path_for("phw", "A39")
        self.assertTrue(os.path.exists(path))

    def test_extract_trigger_event_from_er7(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A39^ADT_A39|MSGID|P|2.5",
            "EVN|A39|20250101010101",
        ])

        trigger = _extract_trigger_event_from_er7(er7)
        self.assertEqual(trigger, "A39")

    def test_extract_trigger_prefers_structure_suffix(self) -> None:
        for msg9 in ("ADT^A31^ADT_A05", "ADT^A28^ADT_A05"):
            er7 = "\r".join([
                f"MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||{msg9}|MSGID|P|2.5",
                "PID|||8888888^^^252^PI||SURNAME^FORENAME",
            ])

            trigger = _extract_trigger_event_from_er7(er7)
            self.assertEqual(trigger, "A05")

    def test_get_schema_xsd_path_for_unknown_flow_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_schema_xsd_path_for("unknown_flow", "A39")