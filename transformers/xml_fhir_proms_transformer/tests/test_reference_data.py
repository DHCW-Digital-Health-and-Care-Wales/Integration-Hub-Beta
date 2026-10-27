"""Tests for the wiki-derived lookup tables.

These are direct ports of the JavaScript functions on the INSE wiki page
`.../PROMS/WPAS_To_PROMS/Javascript Functions`, so every documented code is
asserted, along with the wiki's "return the input unchanged" fallback.
"""

import os
import unittest
from unittest import mock

from xml_fhir_proms_transformer.reference_data import (
    DHA_CODE_NAMES,
    NHS_CERTIFICATION_DISPLAYS,
    StaticReferenceDataResolver,
    dha_code_name,
    nhs_certification_display,
)
from xml_fhir_proms_transformer.source_systems import (
    get_pas_identifier_system,
    get_source_system,
)


class TestNhsCertification(unittest.TestCase):
    def test_all_documented_codes_map_to_their_display(self) -> None:
        expected = {
            "01": "Number present & traced",
            "02": "Number present but not traced",
            "03": "Trace required",
            "04": "Trace attempted - no match or multiple match found",
            "05": "Trace needs to be resolved (NHS number or patient detail conflict)",
            "06": "Trace in progress",
            "07": "Number not present and trace not required",
            "08": "Trace postponed (baby under six weeks old)",
        }
        self.assertEqual(NHS_CERTIFICATION_DISPLAYS, expected)
        for code, display in expected.items():
            with self.subTest(code=code):
                self.assertEqual(nhs_certification_display(code), display)

    def test_unknown_code_is_returned_unchanged(self) -> None:
        # Matches the wiki function, which returns its input when unrecognised.
        self.assertEqual(nhs_certification_display("99"), "99")

    def test_missing_code_returns_none(self) -> None:
        self.assertIsNone(nhs_certification_display(""))
        self.assertIsNone(nhs_certification_display(None))


class TestDhaCode(unittest.TestCase):
    def test_all_documented_codes_map_to_their_health_board(self) -> None:
        expected = {
            "7A1": "BETSI CADWALADR UNIVERSITY LHB",
            "7A2": "HYWEL DDA UNIVERSITY LHB",
            "7A3": "SWANSEA BAY UNIVERSITY LOCAL HEALTH BOARD",
            "7A5": "CWM TAF MORGANNWG UNIVERSITY LOCAL HEALTH BOARD",
            "7A6": "ANEURIN BEVAN UNIVERSITY LHB",
            "7A7": "POWYS TEACHING LOCAL HEALTH BOARD",
        }
        self.assertEqual(DHA_CODE_NAMES, expected)
        for code, name in expected.items():
            with self.subTest(code=code):
                self.assertEqual(dha_code_name(code), name)

    def test_lookup_is_case_insensitive(self) -> None:
        self.assertEqual(dha_code_name("7a3"), "SWANSEA BAY UNIVERSITY LOCAL HEALTH BOARD")

    def test_unknown_code_is_returned_unchanged(self) -> None:
        self.assertEqual(dha_code_name("9Z9"), "9Z9")

    def test_missing_code_returns_none(self) -> None:
        self.assertIsNone(dha_code_name(""))


class TestSourceSystems(unittest.TestCase):
    def test_all_routed_system_ids_have_a_pas_identifier_url(self) -> None:
        # The eight SYSTEM_IDs in the wiki's ROUTING_RULES_WPAS table.
        expected = {
            "108": "https://fhir.sbuhb.nhs.wales/Id/pas-identifier",
            "109": "https://fhir.bcuhb.nhs.wales/Id/central-pas-identifier",
            "139": "https://fhir.abuhb.nhs.wales/Id/pas-identifier",
            "149": "https://fhir.hduhb.nhs.wales/Id/pas-identifier",
            "170": "https://fhir.pthb.nhs.wales/Id/pas-identifier",
            "126": "https://fhir.ctmuhb.nhs.wales/Id/pas-identifier",
            "310": "https://fhir.vunhst.nhs.wales/Id/pas-identifier",
        }
        for system_id, url in expected.items():
            with self.subTest(system_id=system_id):
                self.assertEqual(get_pas_identifier_system(system_id), url)

    def test_non_wpas_health_boards_are_not_sources(self) -> None:
        # 103 is Princess of Wales (PIMS) and 140 is Cardiff and Vale; neither uses WPAS.
        # 131 was a spreadsheet error for Velindre (310).
        for system_id in ("103", "131", "140"):
            with self.subTest(system_id=system_id):
                self.assertIsNone(get_source_system(system_id))

    def test_source_name_and_endpoint_per_health_board(self) -> None:
        expected = {
            "108": "Swansea Bay Health Board",
            "109": "Betsi Cadwaladr University Health Board",
            "126": "Cwm Taf Morgannwg University Health Board",
            "139": "Aneurin Bevan University Health Board",
            "149": "Hywel Dda University Health Board",
            "170": "Powys Teaching Health Board",
            "310": "Velindre University NHS Trust",
        }
        for system_id, name in expected.items():
            with self.subTest(system_id=system_id):
                source_system = get_source_system(system_id)
                assert source_system is not None
                self.assertEqual(source_system.name, name)
                self.assertEqual(source_system.endpoint, f"https://fhir.nhs.uk/source-system/wpas/{system_id}")

    def test_endpoint_can_be_overridden_by_environment(self) -> None:
        with mock.patch.dict(os.environ, {"WPAS_SOURCE_ENDPOINT_109": "https://psom.bcuhb.example"}):
            source_system = get_source_system("109")
        assert source_system is not None
        self.assertEqual(source_system.endpoint, "https://psom.bcuhb.example")

    def test_unknown_system_id_returns_none(self) -> None:
        self.assertIsNone(get_source_system("999"))
        self.assertIsNone(get_pas_identifier_system("999"))

    def test_missing_system_id_returns_none(self) -> None:
        self.assertIsNone(get_source_system(""))
        self.assertIsNone(get_source_system(None))


class TestStaticReferenceDataResolver(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = StaticReferenceDataResolver()

    def test_gender_codes_map_to_administrative_gender(self) -> None:
        for code, expected in (("M", "male"), ("F", "female"), ("O", "other"), ("U", "unknown")):
            with self.subTest(code=code):
                self.assertEqual(self.resolver.resolve_gender(code), expected)

    def test_numeric_gender_codes_are_supported(self) -> None:
        self.assertEqual(self.resolver.resolve_gender("1"), "male")
        self.assertEqual(self.resolver.resolve_gender("2"), "female")

    def test_unmapped_gender_returns_none(self) -> None:
        # An incorrect gender is worse than a missing one.
        with self.assertLogs("xml_fhir_proms_transformer.reference_data", level="WARNING"):
            self.assertIsNone(self.resolver.resolve_gender("ZZ"))

    def test_language_is_unresolvable_without_the_reference_data_service(self) -> None:
        with self.assertLogs("xml_fhir_proms_transformer.reference_data", level="INFO"):
            self.assertIsNone(self.resolver.resolve_language("CY"))


if __name__ == "__main__":
    unittest.main()
