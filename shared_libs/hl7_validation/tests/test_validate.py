import os
import unittest

from hl7_validation.schemas import get_schema_xsd_path_for
from hl7_validation.validate import (
    XmlValidationError,
    validate_er7_with_flow,
)


class TestSchemaPathResolutionAndTriggerParsing(unittest.TestCase):
    def test_get_schema_xsd_path_for(self) -> None:

        path = get_schema_xsd_path_for("phw", "ADT_A39")
        self.assertTrue(os.path.exists(path))





    def test_validate_uses_built_in_mapping_when_structure_missing(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A31|MSGID|P|2.5",
            "PID|||8888888^^^252^PI||SURNAME^FORENAME",
        ])

        try:
            validate_er7_with_flow(er7, "phw")
        except XmlValidationError as e:
            self.fail(f"Validation should succeed with fallback: {e}")

    def test_get_schema_xsd_path_for_unknown_flow_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_schema_xsd_path_for("unknown_flow", "ADT_A39")
