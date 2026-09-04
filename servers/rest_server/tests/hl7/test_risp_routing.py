"""Tests for RispFlowRouter's multi-destination fan-out."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from hl7_validation import ValidationResult
from hl7apy.parser import parse_message

from rest_server.hl7.exceptions.validation_exception import ValidationException
from rest_server.hl7.risp_routing import MPI_TRANSFORMER_DESTINATION, WRRS_DESTINATION, RispFlowRouter
from tests.hl7.helpers import RISP_A28_MESSAGE, RISP_A40_MESSAGE, RISP_ORU_R01_MESSAGE


class RispFlowRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = RispFlowRouter()

    def test_a28_routes_to_mpi_transformer_only(self) -> None:
        msg = parse_message(RISP_A28_MESSAGE, find_groups=False)
        targets = self.router.resolve_targets(msg, RISP_A28_MESSAGE)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].destination, MPI_TRANSFORMER_DESTINATION)
        self.assertEqual(targets[0].payload, RISP_A28_MESSAGE)
        self.assertFalse(targets[0].is_xml)

    def test_a40_routes_to_both_mpi_transformer_and_wrrs(self) -> None:
        msg = parse_message(RISP_A40_MESSAGE, find_groups=False)
        targets = self.router.resolve_targets(msg, RISP_A40_MESSAGE)

        self.assertEqual(len(targets), 2)
        destinations = {t.destination for t in targets}
        self.assertEqual(destinations, {MPI_TRANSFORMER_DESTINATION, WRRS_DESTINATION})

        mpi_target = next(t for t in targets if t.destination == MPI_TRANSFORMER_DESTINATION)
        self.assertEqual(mpi_target.payload, RISP_A40_MESSAGE)
        self.assertFalse(mpi_target.is_xml)

        wrrs_target = next(t for t in targets if t.destination == WRRS_DESTINATION)
        self.assertTrue(wrrs_target.is_xml)
        self.assertIn("<", wrrs_target.payload)

    def test_oru_r01_routes_to_wrrs_only_after_schema_validation(self) -> None:
        msg = parse_message(RISP_ORU_R01_MESSAGE, find_groups=False)
        fake_xml = "<ORU_R01>...</ORU_R01>"
        with patch(
            "rest_server.hl7.risp_routing.validate_and_convert_parsed_message_with_structure_schema",
            return_value=ValidationResult(
                xml_string=fake_xml,
                structure_id="ORU_R01",
                message_type="ORU",
                trigger_event="R01",
                message_control_id="RISPMSG003",
                is_valid=True,
                error_message=None,
            ),
        ) as mock_validate:
            targets = self.router.resolve_targets(msg, RISP_ORU_R01_MESSAGE)

        mock_validate.assert_called_once_with(msg, RISP_ORU_R01_MESSAGE, "ORU_R01", "ORU_R01_2_5_1")
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].destination, WRRS_DESTINATION)
        self.assertTrue(targets[0].is_xml)
        self.assertEqual(targets[0].payload, fake_xml)

    def test_oru_r01_schema_validation_failure_raises(self) -> None:
        msg = parse_message(RISP_ORU_R01_MESSAGE, find_groups=False)
        with patch(
            "rest_server.hl7.risp_routing.validate_and_convert_parsed_message_with_structure_schema",
            return_value=ValidationResult(
                xml_string="<ORU_R01/>",
                structure_id="ORU_R01",
                message_type="ORU",
                trigger_event="R01",
                message_control_id="RISPMSG003",
                is_valid=False,
                error_message="Missing required OBX segment",
            ),
        ):
            with self.assertRaises(ValidationException) as ctx:
                self.router.resolve_targets(msg, RISP_ORU_R01_MESSAGE)
        self.assertIn("Missing required OBX segment", str(ctx.exception))

    def test_invalid_sender_facility_raises_before_routing(self) -> None:
        bad_message = RISP_A28_MESSAGE.replace("|349|349|", "|999|999|")
        msg = parse_message(bad_message, find_groups=False)
        with self.assertRaises(ValidationException):
            self.router.resolve_targets(msg, bad_message)


if __name__ == "__main__":
    unittest.main()
