from __future__ import annotations

import json
import unittest

from db_sender_trrr.request_payload import MAPPING_MERGE, MAPPING_NHS_ID_UPDATE, TrrrRequest, parse_trrr_request

NHS_ID_UPDATE = {"LIMSIdentifier": "ABC123", "NewIdentifier": "9876543210", "NewIdentifierAssigningAuthority": "NHS"}
MERGE = {
    "OldIdentifier": "OLD-001",
    "OldIdentifierAssigningAuthority": "WLIMS",
    "NewIdentifier": "LIMS-77",
    "NewIdentifierAssigningAuthority": "WLIMS",
}


class TestParseTrrrRequest(unittest.TestCase):
    def test_identifies_nhs_id_update_request_from_body(self) -> None:
        self.assertEqual(
            parse_trrr_request(json.dumps(NHS_ID_UPDATE)), TrrrRequest(MAPPING_NHS_ID_UPDATE, NHS_ID_UPDATE)
        )

    def test_identifies_merge_request_from_body(self) -> None:
        self.assertEqual(parse_trrr_request(json.dumps(MERGE)), TrrrRequest(MAPPING_MERGE, MERGE))

    def test_parameters_are_returned_in_stored_procedure_order(self) -> None:
        reordered = dict(reversed(list(MERGE.items())))

        _, parameters = parse_trrr_request(json.dumps(reordered))

        self.assertEqual(list(parameters), list(MERGE))

    def test_preserves_leading_zeroes(self) -> None:
        payload = {**NHS_ID_UPDATE, "LIMSIdentifier": "001234567", "NewIdentifier": "0001234567"}

        _, parameters = parse_trrr_request(json.dumps(payload))

        self.assertEqual(parameters["LIMSIdentifier"], "001234567")
        self.assertEqual(parameters["NewIdentifier"], "0001234567")

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            parse_trrr_request("MSH|^~\\&|LIMS")

    def test_rejects_non_object_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_trrr_request("[]")

    def test_rejects_empty_object(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing or invalid NHS_ID_UPDATE fields"):
            parse_trrr_request("{}")

    def test_rejects_missing_field(self) -> None:
        payload = {k: v for k, v in NHS_ID_UPDATE.items() if k != "NewIdentifier"}

        with self.assertRaisesRegex(ValueError, "Missing or invalid NHS_ID_UPDATE fields: NewIdentifier"):
            parse_trrr_request(json.dumps(payload))

    def test_rejects_null_and_non_string_fields(self) -> None:
        payload = {**MERGE, "OldIdentifier": None, "NewIdentifier": 12345}

        with self.assertRaisesRegex(ValueError, "Missing or invalid MERGE fields: OldIdentifier, NewIdentifier"):
            parse_trrr_request(json.dumps(payload))

    def test_accepts_blank_unmapped_fields_unchanged(self) -> None:
        # spProcessIdUpdate accepts blank parameters for values the source message did not map.
        payload = {**MERGE, "OldIdentifierAssigningAuthority": "", "NewIdentifierAssigningAuthority": "  "}

        self.assertEqual(parse_trrr_request(json.dumps(payload)), TrrrRequest(MAPPING_MERGE, payload))

    def test_rejects_request_with_every_field_blank(self) -> None:
        payload = {name: "" for name in NHS_ID_UPDATE}

        with self.assertRaisesRegex(ValueError, "All NHS_ID_UPDATE fields are blank"):
            parse_trrr_request(json.dumps(payload))

    def test_rejects_mixed_request_shapes(self) -> None:
        # OldIdentifier makes it a merge, so the NHS-ID-only field is unexpected and nothing is written.
        with self.assertRaisesRegex(ValueError, "Missing or invalid MERGE fields: OldIdentifierAssigningAuthority"):
            parse_trrr_request(json.dumps({**NHS_ID_UPDATE, "OldIdentifier": "X"}))
        with self.assertRaisesRegex(ValueError, "Unexpected fields for MERGE: LIMSIdentifier"):
            parse_trrr_request(json.dumps({**MERGE, "LIMSIdentifier": "X"}))
        # Without OldIdentifier it is an NHS-ID update, so the merge-only field is unexpected.
        with self.assertRaisesRegex(ValueError, "Unexpected fields for NHS_ID_UPDATE: OldIdentifierAssigningAuthority"):
            parse_trrr_request(json.dumps({**NHS_ID_UPDATE, "OldIdentifierAssigningAuthority": "X"}))

    def test_error_messages_do_not_contain_identifier_values(self) -> None:
        payload = {**NHS_ID_UPDATE, "LIMSIdentifier": 1}

        with self.assertRaises(ValueError) as ctx:
            parse_trrr_request(json.dumps(payload))

        self.assertNotIn("9876543210", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
