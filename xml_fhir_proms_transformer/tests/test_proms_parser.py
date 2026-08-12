import unittest

from tests.wpas_messages import (
    EXPLICIT_EVENT_CODE_MESSAGE,
    LEGACY_MESSAGE_TYPE_MESSAGE,
    NESTED_REFERRAL_MESSAGE,
    REFERRAL_MESSAGE,
)
from xml_fhir_proms_transformer.proms_parser import get_message_type, normalise_key, parse_proms_xml


class TestNormaliseKey(unittest.TestCase):
    def test_dialects_collapse_to_the_same_key(self) -> None:
        # WPAS sends camelCase; legacy may use upper snake case. Both must resolve identically.
        self.assertEqual(normalise_key("nhsNumber"), normalise_key("NHS_NUMBER"))
        self.assertEqual(normalise_key("system_id"), normalise_key("SYSTEM_ID"))
        self.assertEqual(normalise_key("nhs-number"), normalise_key("NHS_NUMBER"))


class TestParseProsXml(unittest.TestCase):
    def test_parses_flat_referral_payload(self) -> None:
        message = parse_proms_xml(REFERRAL_MESSAGE)

        self.assertEqual(message.root_tag, "PromsEventRequest")
        self.assertEqual(message.get("system_id"), "149")
        self.assertEqual(message.get("nhsNumber"), "9434765919")
        self.assertEqual(message.get("patientSurname"), "Bevan")
        self.assertEqual(message.get("eventCode"), "REFERRAL")

    def test_field_aliases_resolve_across_dialects(self) -> None:
        message = parse_proms_xml(REFERRAL_MESSAGE)

        # camelCase and UPPER_SNAKE_CASE resolve to the same normalised key
        self.assertEqual(message.get("nhsNumber", "NHS_NUMBER"), message.get("NHS_NUMBER"))

    def test_parses_nested_payload(self) -> None:
        # Leaf elements are indexed regardless of nesting depth
        message = parse_proms_xml(NESTED_REFERRAL_MESSAGE)

        self.assertEqual(message.root_tag, "PromsEventRequest")
        self.assertEqual(message.get("system_id"), "149")
        self.assertEqual(message.get("nhsNumber"), "9434766019")
        self.assertEqual(message.get("patientSurname"), "Nested")

    def test_missing_field_returns_empty_string(self) -> None:
        message = parse_proms_xml(REFERRAL_MESSAGE)

        self.assertEqual(message.get("consultant_gmc"), "")
        self.assertFalse(message.has("consultant_gmc"))

    def test_namespaced_elements_are_supported(self) -> None:
        message = parse_proms_xml(
            "<PromsEventRequest xmlns='urn:wpas:proms'><nhsNumber>9434765919</nhsNumber></PromsEventRequest>"
        )

        self.assertEqual(message.root_tag, "PromsEventRequest")
        self.assertEqual(message.get("nhsNumber"), "9434765919")

    def test_malformed_xml_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_proms_xml("<PromsEventRequest><nhsNumber>123</PromsEventRequest>")

    def test_empty_payload_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_proms_xml("   ")


class TestGetMessageType(unittest.TestCase):
    def test_prefers_event_code_field(self) -> None:
        message = parse_proms_xml(REFERRAL_MESSAGE)
        self.assertEqual(get_message_type(message), "REFERRAL")

    def test_accepts_explicit_event_code_in_generic_root(self) -> None:
        message = parse_proms_xml(EXPLICIT_EVENT_CODE_MESSAGE)
        self.assertEqual(get_message_type(message), "SURGERY")

    def test_falls_back_to_legacy_message_type_field(self) -> None:
        message = parse_proms_xml(LEGACY_MESSAGE_TYPE_MESSAGE)
        self.assertEqual(get_message_type(message), "REFERRAL")

    def test_returns_none_when_no_routing_field_present(self) -> None:
        message = parse_proms_xml("<PromsEventRequest><nhsNumber>9434765919</nhsNumber></PromsEventRequest>")
        self.assertIsNone(get_message_type(message))


if __name__ == "__main__":
    unittest.main()
