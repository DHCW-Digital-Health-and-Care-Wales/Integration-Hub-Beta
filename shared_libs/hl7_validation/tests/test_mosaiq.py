import unittest

from hl7_validation import validate_er7_with_flow_schema
from hl7_validation.validate import XmlValidationError


class TestMosaiqMessages(unittest.TestCase):
    """Schema validation tests for the Mosaiq flow (HL7 v2.5, ADT A28/A31/A40).

    Mosaiq is a Paris-style passthrough flow. A28/A31 use the ADT_A05 structure and
    A40 (merge) uses the ADT_A39 structure, matching the shared HL7 v2.5 schemas.
    """

    def test_mosaiq_a31_a05_schema_validation_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|285|285|100|100|2025-05-05 23:23:30||ADT^A31^ADT_A05|"
            "202505052323300000000000|P|2.5|||||GBR||EN",
            "EVN|A05|20250502092900|20250505232330|||20250505232330",
            "PID|||8888888^^^285^PI~4444444444^^^NHS^NH||SURNAME^FORENAME",
            "PV1||"
        ])

        validate_er7_with_flow_schema(er7, "mosaiq")

    def test_mosaiq_a28_a05_schema_validation_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|285|285|100|100|2025-05-05 23:23:30||ADT^A28^ADT_A05|"
            "202505052323300000000000|P|2.5|||||GBR||EN",
            "EVN|A05|20250502092900|20250505232330|||20250505232330",
            "PID|||8888888^^^285^PI~4444444444^^^NHS^NH||SURNAME^FORENAME",
            "PV1||"
        ])

        validate_er7_with_flow_schema(er7, "mosaiq")

    def test_mosaiq_a40_a39_schema_validation_successful(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|285|285|100|100|2025-05-05 23:23:32||ADT^A40^ADT_A39||P|2.5|||||GBR||EN",
            "EVN|A39|20250502092900|20250505232332|||20250505232332",
            "PID|||8888888^^^285^PI~4444444444^^^NHS^NH||MYSURNAME^MYFNAME^MYMNAME^^MR||19990101|M|^^||"
            "99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H~^^^^^^||^^^~|||||||||||||||||||01",
            "PD1|||^^W00000^|G999999",
            "MRG|||7777777^^^285^PI~5555555555^^^NHS^NH",
            "PV1||"
        ])

        validate_er7_with_flow_schema(er7, "mosaiq")

    def test_mosaiq_a05_incorrectly_structured_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|285|285|100|100|2025-05-05 23:23:30||ADT^A31^ADT_A05|"
            "202505052323300000000000|P|2.5|||||GBR||EN",
            "EVN|A05|20250502092900|20250505232330|||20250505232330",
            "XXX|This is an invalid segment not in the schema",  # Invalid segment
            "PID|||8888888^^^285^PI~4444444444^^^NHS^NH||SURNAME^FORENAME||19990101|M",
            "PV1||"
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "mosaiq")
        error_message = str(context.exception)
        self.assertIn("Unable to parse ER7 message", error_message)

    def test_mosaiq_a05_correctly_structured_invalid_data_validation_failure(self) -> None:
        er7 = "\r".join([
            "MSH|^~\\&|285|285|100|100|2025-05-05 23:23:30||ADT^A31^ADT_A05|"
            "202505052323300000000000|P|2.5|||||GBR||EN",
            "EVN|A05|20250502092900|20250505232330|||20250505232330",
            "PID|||8888888^^^285^PI~4444444444^^^NHS^NH||SURNAME^FORENAME"
            # Missing PV1 segment which is required according to ADT_A05 schema
        ])

        with self.assertRaises(XmlValidationError) as context:
            validate_er7_with_flow_schema(er7, "mosaiq")
        error_message = str(context.exception)
        self.assertIn("Tag '{urn:hl7-org:v2xml}PV1' expected", error_message)


if __name__ == "__main__":
    unittest.main()
