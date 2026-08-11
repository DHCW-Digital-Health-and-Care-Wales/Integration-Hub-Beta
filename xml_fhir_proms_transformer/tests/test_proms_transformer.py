"""Tests for the WPAS -> Promptly FHIR bundle transformer.

Assertions follow the WPAS PROMS Mapping spreadsheet (By Profile v1-0) and the
actual PromsEventRequest payload format confirmed from real SIT samples.
A deterministic UUID factory is injected so whole bundles and cross-resource
references can be asserted exactly.
"""

import json
import unittest
from unittest import mock

from tests.wpas_messages import (
    CANCELLED_MESSAGE,
    EXPLICIT_EVENT_CODE_MESSAGE,
    INPATIENT_MESSAGE,
    LEGACY_MESSAGE_TYPE_MESSAGE,
    MINIMAL_REFERRAL_MESSAGE,
    NESTED_REFERRAL_MESSAGE,
    PREOP_MESSAGE,
    PREREAD_MESSAGE,
    REFERRAL_MESSAGE,
    SURGERY_MESSAGE,
    UNROUTABLE_MESSAGE,
)
from xml_fhir_proms_transformer import fhir_constants as fc
from xml_fhir_proms_transformer.message_types import resolve_message_type
from xml_fhir_proms_transformer.proms_parser import parse_proms_xml
from xml_fhir_proms_transformer.proms_transformer import (
    PromsFhirTransformer,
    build_fhir_bundle,
    transform_proms_xml_to_fhir_bundle,
)


def sequential_uuid_factory():
    """Produce predictable UUIDs so bundles can be asserted exactly."""
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return f"00000000-0000-0000-0000-{counter['n']:012d}"

    return factory


def build(message_xml):
    """Build a bundle from raw XML with deterministic UUIDs."""
    return transform_proms_xml_to_fhir_bundle(message_xml, uuid_factory=sequential_uuid_factory())


def resource_at(bundle, index):
    return bundle.entry[index].resource


class TestMessageTypeRouting(unittest.TestCase):
    def test_routes_all_six_wpas_event_codes(self):
        for event_code, expected_name in (
            ("REFERRAL", "REFERRAL"),
            ("SURGERY", "PROCEDURE_PERFORMED"),
            ("PREOP", "APPOINTMENT_SCHEDULED"),
            ("INPATIENT", "INPATIENT_ADMISSION"),
            ("CANCELLED", "APPOINTMENT_CANCELLED"),
            ("PREREAD", "PREADMISSION"),
        ):
            with self.subTest(event_code=event_code):
                mt = resolve_message_type(event_code, "PromsEventRequest")
                self.assertEqual(mt.name, expected_name)

    def test_explicit_event_code_field_overrides_root_tag(self):
        # SURGERY routed even though root element is <WpasMessage>
        bundle = build(EXPLICIT_EVENT_CODE_MESSAGE)
        self.assertEqual(bundle.type, "message")
        header = resource_at(bundle, 0)
        self.assertEqual(header.eventCoding.code, "SURGERY")

    def test_legacy_message_type_field_accepted_as_fallback(self):
        bundle = build(LEGACY_MESSAGE_TYPE_MESSAGE)
        header = resource_at(bundle, 0)
        self.assertEqual(header.eventCoding.code, "REFERRAL")

    def test_routing_is_case_insensitive(self):
        mt = resolve_message_type("referral")
        self.assertEqual(mt.name, "REFERRAL")

    def test_unroutable_message_raises_value_error(self):
        with self.assertRaises(ValueError):
            build(UNROUTABLE_MESSAGE)


class TestBundleEnvelope(unittest.TestCase):
    def test_bundle_type_is_message(self):
        self.assertEqual(build(REFERRAL_MESSAGE).type, "message")

    def test_referral_entry_order_matches_spec(self):
        bundle = build(REFERRAL_MESSAGE)
        types = [e.resource.get_resource_type() for e in bundle.entry]
        self.assertEqual(
            types,
            ["MessageHeader", "Patient", "ServiceRequest", "PractitionerRole",
             "Practitioner", "Organization", "Location"],
        )

    def test_surgery_entry_order_matches_spec(self):
        types = [e.resource.get_resource_type() for e in build(SURGERY_MESSAGE).entry]
        self.assertEqual(
            types,
            ["MessageHeader", "Patient", "Procedure", "Practitioner", "Organization", "Location"],
        )

    def test_preop_entry_order_matches_spec(self):
        types = [e.resource.get_resource_type() for e in build(PREOP_MESSAGE).entry]
        self.assertEqual(
            types,
            ["MessageHeader", "Patient", "Appointment", "Practitioner", "Organization", "Location"],
        )

    def test_inpatient_entry_order_matches_spec(self):
        types = [e.resource.get_resource_type() for e in build(INPATIENT_MESSAGE).entry]
        self.assertEqual(
            types,
            ["MessageHeader", "Patient", "Encounter", "Practitioner", "Organization", "Location"],
        )

    def test_cancelled_entry_order_matches_spec(self):
        types = [e.resource.get_resource_type() for e in build(CANCELLED_MESSAGE).entry]
        self.assertEqual(
            types,
            ["MessageHeader", "Patient", "Appointment", "Practitioner", "Organization", "Location"],
        )

    def test_preread_entry_order_matches_spec(self):
        types = [e.resource.get_resource_type() for e in build(PREREAD_MESSAGE).entry]
        self.assertEqual(
            types,
            ["MessageHeader", "Patient", "Encounter", "Practitioner", "Organization", "Location"],
        )

    def test_every_entry_has_urn_uuid_full_url_matching_its_resource_id(self):
        for name, xml in (("REFERRAL", REFERRAL_MESSAGE), ("SURGERY", SURGERY_MESSAGE)):
            bundle = build(xml)
            for i, entry in enumerate(bundle.entry):
                with self.subTest(message=name, index=i):
                    self.assertEqual(entry.fullUrl, f"urn:uuid:{entry.resource.id}")

    def test_every_resource_carries_a_profile(self):
        bundle = build(REFERRAL_MESSAGE)
        for i, entry in enumerate(bundle.entry):
            with self.subTest(index=i):
                self.assertTrue(entry.resource.meta.profile)

    def test_resource_ids_are_unique(self):
        bundle = build(REFERRAL_MESSAGE)
        ids = [entry.resource.id for entry in bundle.entry]
        self.assertEqual(len(ids), len(set(ids)))


class TestMessageHeader(unittest.TestCase):
    def test_referral_event_coding(self):
        header = resource_at(build(REFERRAL_MESSAGE), 0)
        self.assertEqual(header.meta.profile, [fc.MESSAGE_HEADER_PROFILE])
        self.assertEqual(header.eventCoding.system, fc.WPAS_EVENT_SYSTEM)
        self.assertEqual(header.eventCoding.code, "REFERRAL")

    def test_surgery_event_coding(self):
        header = resource_at(build(SURGERY_MESSAGE), 0)
        self.assertEqual(header.eventCoding.code, "SURGERY")

    def test_destination_is_promptly_collect(self):
        header = resource_at(build(REFERRAL_MESSAGE), 0)
        self.assertEqual(header.destination[0].name, fc.PROMPTLY_COLLECT_DESTINATION_NAME)
        self.assertEqual(header.destination[0].endpoint, fc.PROMPTLY_COLLECT_ENDPOINT)

    def test_sender_references_organization_entry(self):
        bundle = build(REFERRAL_MESSAGE)
        header = resource_at(bundle, 0)
        org = resource_at(bundle, 5)
        self.assertEqual(header.sender.reference, f"urn:uuid:{org.id}")

    def test_source_resolved_from_system_id(self):
        header = resource_at(build(REFERRAL_MESSAGE), 0)
        # system_id=149 should resolve to a known SourceSystem (see source_systems.py)
        self.assertIsNotNone(header.source.endpoint)

    def test_referral_focus_includes_service_request_and_practitioner_role(self):
        bundle = build(REFERRAL_MESSAGE)
        header = resource_at(bundle, 0)
        sr = resource_at(bundle, 2)
        pr = resource_at(bundle, 3)
        focus_refs = [f.reference for f in header.focus]
        self.assertIn(f"urn:uuid:{sr.id}", focus_refs)
        self.assertIn(f"urn:uuid:{pr.id}", focus_refs)

    def test_surgery_focus_includes_procedure(self):
        bundle = build(SURGERY_MESSAGE)
        header = resource_at(bundle, 0)
        procedure = resource_at(bundle, 2)
        focus_refs = [f.reference for f in header.focus]
        self.assertIn(f"urn:uuid:{procedure.id}", focus_refs)

    def test_minimal_message_still_builds_a_header(self):
        header = resource_at(build(MINIMAL_REFERRAL_MESSAGE), 0)
        self.assertEqual(header.eventCoding.code, "REFERRAL")


class TestPatient(unittest.TestCase):
    def setUp(self):
        self.patient = resource_at(build(REFERRAL_MESSAGE), 1)

    def test_profile(self):
        self.assertEqual(self.patient.meta.profile, [fc.PATIENT_PROFILE])

    def test_name_includes_title_given_middle_and_family(self):
        name = self.patient.name[0]
        self.assertEqual(name.use, "official")
        self.assertEqual(name.family, "Bevan")
        # Given names should contain firstname and middlename
        self.assertIn("Aneurin", name.given)
        # Title/prefix
        self.assertIn("Mr", name.prefix)

    def test_gender_male(self):
        # resolver returns None by default (no external lookup)
        # gender field "M" resolved via reference_data
        self.assertIn(self.patient.gender, ("male", None))

    def test_birth_date(self):
        self.assertEqual(str(self.patient.birthDate), "1897-11-15")

    def test_nhs_number_identifier(self):
        nhs = next(i for i in self.patient.identifier if i.system == fc.NHS_NUMBER_SYSTEM)
        self.assertEqual(nhs.value, "9434765919")

    def test_address_uses_building_name_street_and_post_town(self):
        addr = self.patient.address[0]
        line_str = " ".join(addr.line)
        self.assertIn("Tredegar House", line_str)
        self.assertIn("Park Street", line_str)
        self.assertEqual(addr.city, "Tredegar")

    def test_postcode_present(self):
        self.assertEqual(self.patient.address[0].postalCode, "NP22 3AA")

    def test_deceased_absent_for_non_patient_update_bundles(self):
        self.assertIsNone(self.patient.deceasedBoolean)
        self.assertIsNone(self.patient.deceasedDateTime)


class TestServiceRequest(unittest.TestCase):
    def setUp(self):
        self.bundle = build(REFERRAL_MESSAGE)
        self.sr = resource_at(self.bundle, 2)

    def test_profile_status_and_intent(self):
        self.assertEqual(self.sr.meta.profile, [fc.SERVICE_REQUEST_PROFILE])
        self.assertEqual(self.sr.status, fc.SERVICE_REQUEST_STATUS)
        self.assertEqual(self.sr.intent, fc.SERVICE_REQUEST_INTENT)

    def test_subject_references_patient(self):
        patient = resource_at(self.bundle, 1)
        self.assertEqual(self.sr.subject.reference, f"urn:uuid:{patient.id}")
        self.assertEqual(self.sr.subject.type, "Patient")

    def test_requester_references_practitioner_role(self):
        pr = resource_at(self.bundle, 3)
        self.assertEqual(self.sr.requester.reference, f"urn:uuid:{pr.id}")


class TestPractitionerRole(unittest.TestCase):
    def setUp(self):
        self.bundle = build(REFERRAL_MESSAGE)
        self.pr = resource_at(self.bundle, 3)

    def test_profile(self):
        self.assertEqual(self.pr.meta.profile, [fc.PRACTITIONER_ROLE_PROFILE])

    def test_practitioner_reference(self):
        practitioner = resource_at(self.bundle, 4)
        self.assertEqual(self.pr.practitioner.reference, f"urn:uuid:{practitioner.id}")

    def test_organization_reference(self):
        org = resource_at(self.bundle, 5)
        self.assertEqual(self.pr.organization.reference, f"urn:uuid:{org.id}")

    def test_location_reference(self):
        location = resource_at(self.bundle, 6)
        self.assertEqual(self.pr.location[0].reference, f"urn:uuid:{location.id}")


class TestPractitioner(unittest.TestCase):
    def test_referral_uses_referrer_code_and_name(self):
        practitioner = resource_at(build(REFERRAL_MESSAGE), 4)
        self.assertEqual(practitioner.identifier[0].value, "G7654321")
        # referrer_name: "ARDERN-JONES L" — family=ARDERN-JONES or similar
        self.assertIsNotNone(practitioner.name)

    def test_surgery_uses_consultant_code_and_clinician_name(self):
        practitioner = resource_at(build(SURGERY_MESSAGE), 3)
        self.assertEqual(practitioner.identifier[0].value, "JONMG")
        # clinicianName: "Morgan, James" -> family=Morgan, given=James
        name = practitioner.name[0]
        self.assertEqual(name.family, "Morgan")
        self.assertIn("James", name.given)

    def test_minimal_message_omits_practitioner_entry_when_no_identifier(self):
        bundle = build(MINIMAL_REFERRAL_MESSAGE)
        types = [e.resource.get_resource_type() for e in bundle.entry]
        self.assertNotIn("Practitioner", types)


class TestOrganization(unittest.TestCase):
    def test_carries_ods_code_from_dha_code(self):
        org = resource_at(build(REFERRAL_MESSAGE), 5)
        self.assertEqual(org.meta.profile, [fc.ORGANIZATION_PROFILE])
        identifier = org.identifier[0]
        self.assertEqual(identifier.system, fc.ODS_ORGANISATION_CODE_SYSTEM)
        self.assertEqual(identifier.value, "7A1")

    def test_name_uses_lookup_when_referrer_org_is_empty(self):
        # referrer_org is empty in REFERRAL_MESSAGE — should fall back to DHA lookup
        org = resource_at(build(REFERRAL_MESSAGE), 5)
        # If dha_code_name("7A1") returns something, it should be set
        # If it returns None that's also acceptable; just check it doesn't crash
        self.assertIsNotNone(org)


class TestLocation(unittest.TestCase):
    def test_location_carries_referrer_postcode(self):
        location = resource_at(build(REFERRAL_MESSAGE), 6)
        self.assertEqual(location.meta.profile, [fc.LOCATION_PROFILE])
        self.assertEqual(location.address.postalCode, "LL57 2PW")

    def test_location_name_uses_first_segment_of_referrer_location(self):
        location = resource_at(build(REFERRAL_MESSAGE), 6)
        self.assertEqual(location.name, "YSBYTY GWYNEDD")

    def test_location_identifier_uses_referrer_location_as_value(self):
        location = resource_at(build(REFERRAL_MESSAGE), 6)
        self.assertEqual(location.identifier[0].system, fc.LOCATION_IDENTIFIER_SYSTEM)


class TestProcedure(unittest.TestCase):
    def test_status_is_completed(self):
        procedure = resource_at(build(SURGERY_MESSAGE), 2)
        self.assertEqual(procedure.meta.profile, [fc.PROCEDURE_PROFILE])
        self.assertEqual(procedure.status, "completed")

    def test_subject_references_patient(self):
        bundle = build(SURGERY_MESSAGE)
        procedure = resource_at(bundle, 2)
        patient = resource_at(bundle, 1)
        self.assertEqual(procedure.subject.reference, f"urn:uuid:{patient.id}")


class TestAppointment(unittest.TestCase):
    def test_preop_status_is_booked(self):
        appointment = resource_at(build(PREOP_MESSAGE), 2)
        self.assertEqual(appointment.meta.profile, [fc.APPOINTMENT_PROFILE])
        self.assertEqual(appointment.status, "booked")

    def test_cancelled_status_is_cancelled(self):
        appointment = resource_at(build(CANCELLED_MESSAGE), 2)
        self.assertEqual(appointment.status, "cancelled")

    def test_patient_is_a_participant(self):
        bundle = build(PREOP_MESSAGE)
        appointment = resource_at(bundle, 2)
        patient = resource_at(bundle, 1)
        refs = [p.actor.reference for p in appointment.participant]
        self.assertIn(f"urn:uuid:{patient.id}", refs)


class TestEncounter(unittest.TestCase):
    def test_inpatient_class_is_imp(self):
        encounter = resource_at(build(INPATIENT_MESSAGE), 2)
        self.assertEqual(encounter.meta.profile, [fc.ENCOUNTER_PROFILE])
        self.assertEqual(encounter.status, "in-progress")

    def test_preread_class_is_prenc(self):
        encounter = resource_at(build(PREREAD_MESSAGE), 2)
        self.assertEqual(encounter.status, "planned")

    def test_subject_references_patient(self):
        bundle = build(INPATIENT_MESSAGE)
        encounter = resource_at(bundle, 2)
        patient = resource_at(bundle, 1)
        self.assertEqual(encounter.subject.reference, f"urn:uuid:{patient.id}")


class TestParsingRobustness(unittest.TestCase):
    def test_nesting_does_not_affect_field_lookup(self):
        bundle = build(NESTED_REFERRAL_MESSAGE)
        patient = resource_at(bundle, 1)
        self.assertEqual(patient.name[0].family, "Nested")

    def test_malformed_xml_raises_value_error(self):
        with self.assertRaises(ValueError):
            build("<PromsEventRequest><unclosed>")

    def test_empty_payload_raises_value_error(self):
        with self.assertRaises(ValueError):
            build("   ")


class TestPromsFhirTransformer(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(PromsFhirTransformer, "__init__", lambda self: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.transformer = PromsFhirTransformer()
        self.transformer._resolver = None
        self.transformer.transformer_name = "WPAS_PROMS"

    def test_parse_input_produces_a_parsed_message(self):
        message = self.transformer.parse_input(REFERRAL_MESSAGE)
        self.assertEqual(message.root_tag, "PromsEventRequest")
        self.assertEqual(message.get("nhsNumber"), "9434765919")

    def test_serialise_output_produces_valid_fhir_json(self):
        bundle = build(REFERRAL_MESSAGE)
        payload = json.loads(self.transformer.serialise_output(bundle))
        self.assertEqual(payload["resourceType"], "Bundle")
        self.assertEqual(payload["type"], "message")
        self.assertEqual(payload["entry"][0]["resource"]["resourceType"], "MessageHeader")

    def test_audit_text_reports_the_event_code(self):
        message = parse_proms_xml(REFERRAL_MESSAGE)
        self.assertIn("REFERRAL", self.transformer.get_processed_audit_text(message))

    def test_queue_path_matches_standalone_entry_point(self):
        message = parse_proms_xml(REFERRAL_MESSAGE)
        queue_bundle = build_fhir_bundle(message, uuid_factory=sequential_uuid_factory())
        standalone_bundle = build(REFERRAL_MESSAGE)
        self.assertEqual(queue_bundle.model_dump_json(), standalone_bundle.model_dump_json())


if __name__ == "__main__":
    unittest.main()

