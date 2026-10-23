from __future__ import annotations

import unittest
from unittest.mock import patch

from hl7apy.parser import parse_message

from hl7_lims_wrrs_transformer.app_config import MappingTypeConfig
from hl7_lims_wrrs_transformer.classifier import classify_message
from tests.messages import (
    A04_NHS_AND_LIMS,
    A31_LIMS_ONLY,
    A31_NHS_AND_LIMS,
    A40_LIMS_ONLY,
    A40_NHS_AND_LIMS,
    A40_NHS_ONLY_NO_MRG,
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
        with patch("hl7_lims_wrrs_transformer.classifier.get_cx_4_hd_1_segment_codes_from_pid_field", return_value=[]):
            self.assertEqual(classify_message(message, _TYPES), [])

    def test_custom_mapping_type_values_are_returned(self) -> None:
        custom = MappingTypeConfig(nhs_id_update="X_NHS", a40="X_A40")
        self.assertEqual(classify_message(parse_message(A40_NHS_AND_LIMS), custom), ["X_NHS", "X_A40"])


if __name__ == "__main__":
    unittest.main()
