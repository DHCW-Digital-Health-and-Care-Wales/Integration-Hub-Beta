from __future__ import annotations

import unittest
from unittest.mock import patch

from hl7apy.parser import parse_message

from hl7_lims_wrrs_transformer.app_config import MappingTypeConfig
from hl7_lims_wrrs_transformer.classifier import classify_message
from tests.lims_xml import Identifier, LimsMessage, Patient, lims_er7
from tests.messages import (
    A04_NHS_AND_LIMS,
    A31_LIMS_ONLY,
    A31_NHS_AND_LIMS,
    A40_LIMS_ONLY,
    A40_NHS_AND_LIMS,
    A40_NHS_ONLY_NO_MRG,
    A40_SPLIT_ACROSS_PATIENT_GROUPS,
)

_TYPES = MappingTypeConfig(nhs_id_update="LIMS_NHS_ID_UPDATE", a40="ADT_A40")


def _classify(er7: str) -> list[str]:
    return classify_message(parse_message(er7), _TYPES)


class TestClassifier(unittest.TestCase):
    def test_a31_with_nhs_and_lims_ids_is_nhs_id_update_only(self) -> None:
        self.assertEqual(_classify(A31_NHS_AND_LIMS), ["LIMS_NHS_ID_UPDATE"])

    def test_a40_with_nhs_and_lims_ids_matches_both_rules(self) -> None:
        self.assertEqual(_classify(A40_NHS_AND_LIMS), ["LIMS_NHS_ID_UPDATE", "ADT_A40"])

    def test_a40_without_nhs_id_is_a40_only(self) -> None:
        self.assertEqual(_classify(A40_LIMS_ONLY), ["ADT_A40"])

    def test_a40_is_classified_on_trigger_event_without_requiring_mrg(self) -> None:
        # Approved rule is MSH.9.2 = 'A40'; a missing MRG is left for the mapping stage to reject.
        self.assertEqual(_classify(A40_NHS_ONLY_NO_MRG), ["ADT_A40"])

    def test_a31_missing_nhs_or_lims_identifier_is_unsupported(self) -> None:
        self.assertEqual(_classify(A31_LIMS_ONLY), [])

    def test_unsupported_trigger_event_is_unsupported_even_with_matching_ids(self) -> None:
        self.assertEqual(_classify(A04_NHS_AND_LIMS), [])

    def test_message_without_pid_is_unsupported(self) -> None:
        message = parse_message(A31_NHS_AND_LIMS)
        with patch("hl7_lims_wrrs_transformer.classifier._find_pid_segments", return_value=[]):
            self.assertEqual(classify_message(message, _TYPES), [])

    def test_identifiers_split_across_patient_groups_do_not_satisfy_nhs_rule(self) -> None:
        # NHS in one PID and 328 in another: neither PID-3 meets the rule on its own.
        self.assertEqual(_classify(A40_SPLIT_ACROSS_PATIENT_GROUPS), ["ADT_A40"])

    def test_custom_mapping_type_values_are_returned(self) -> None:
        custom = MappingTypeConfig(nhs_id_update="X_NHS", a40="X_A40")
        self.assertEqual(classify_message(parse_message(A40_NHS_AND_LIMS), custom), ["X_NHS", "X_A40"])


NHS = Identifier("9876543210", "NHS", "NH")
LIMS = Identifier("B1", "328")
OTHER = Identifier("X9", "ABC")


def _classify_xml(message: LimsMessage) -> list[str]:
    # Real xml_to_er7 output: empty components are dropped (e.g. "B1^328^PI", authority in CX.2).
    return _classify(lims_er7(message))


class TestCompactedEr7FromRestServer(unittest.TestCase):
    def test_fixture_is_really_compacted(self) -> None:
        er7 = lims_er7(LimsMessage("A31", "ADT_A05", [Patient([NHS, LIMS])]))
        self.assertIn("9876543210^NHS^NH~B1^328^PI", er7)

    def test_a31_with_nhs_and_lims_is_nhs_id_update(self) -> None:
        self.assertEqual(
            _classify_xml(LimsMessage("A31", "ADT_A05", [Patient([NHS, LIMS])])), ["LIMS_NHS_ID_UPDATE"]
        )

    def test_a40_with_nhs_and_lims_and_mrg_matches_both_rules(self) -> None:
        message = LimsMessage("A40", "ADT_A39", [Patient([NHS, LIMS], merged_id=Identifier("OLD", "328"))])
        self.assertEqual(_classify_xml(message), ["LIMS_NHS_ID_UPDATE", "ADT_A40"])

    def test_a40_with_lims_only_is_a40_only(self) -> None:
        message = LimsMessage("A40", "ADT_A39", [Patient([LIMS], merged_id=Identifier("OLD", "328"))])
        self.assertEqual(_classify_xml(message), ["ADT_A40"])

    def test_a31_missing_nhs_is_unsupported(self) -> None:
        self.assertEqual(_classify_xml(LimsMessage("A31", "ADT_A05", [Patient([LIMS])])), [])

    def test_a31_missing_lims_is_unsupported(self) -> None:
        self.assertEqual(_classify_xml(LimsMessage("A31", "ADT_A05", [Patient([NHS])])), [])

    def test_a40_with_multiple_patient_groups_finds_authorities_in_one_pid(self) -> None:
        message = LimsMessage(
            "A40",
            "ADT_A39",
            [
                Patient([LIMS], merged_id=Identifier("O1", "328")),
                Patient([NHS, LIMS], merged_id=Identifier("O2", "328")),
            ],
        )
        self.assertEqual(_classify_xml(message), ["LIMS_NHS_ID_UPDATE", "ADT_A40"])

    def test_nhs_and_lims_in_different_pids_do_not_match(self) -> None:
        message = LimsMessage(
            "A40",
            "ADT_A39",
            [Patient([NHS], merged_id=Identifier("O1", "328")), Patient([LIMS], merged_id=Identifier("O2", "328"))],
        )
        self.assertEqual(_classify_xml(message), ["ADT_A40"])

    def test_identifier_value_328_with_other_authority_does_not_count(self) -> None:
        # CX.1 (the ID value itself) is never an authority, even when it equals "328".
        message = LimsMessage("A31", "ADT_A05", [Patient([NHS, Identifier("328", "ABC")])])
        self.assertEqual(_classify_xml(message), [])

    def test_identifier_value_nhs_with_other_authority_does_not_count(self) -> None:
        message = LimsMessage("A31", "ADT_A05", [Patient([Identifier("NHS", "ABC"), LIMS])])
        self.assertEqual(_classify_xml(message), [])

    def test_unrelated_extra_identifier_repetition_is_ignored(self) -> None:
        self.assertEqual(
            _classify_xml(LimsMessage("A31", "ADT_A05", [Patient([NHS, OTHER, LIMS])])), ["LIMS_NHS_ID_UPDATE"]
        )

    def test_codes_are_not_matched_across_component_boundaries_of_different_repetitions(self) -> None:
        # "NHS" as CX.1 of one repetition and "328" as the authority of another must not satisfy the rule.
        message = LimsMessage("A31", "ADT_A05", [Patient([Identifier("NHS", "ABC"), Identifier("B1", "328")])])
        self.assertEqual(_classify_xml(message), [])


if __name__ == "__main__":
    unittest.main()
