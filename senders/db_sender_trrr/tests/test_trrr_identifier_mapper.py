from __future__ import annotations

from db_sender_trrr.identifier_mapper import (
    MAPPING_MERGE,
    MAPPING_NHS_ID_UPDATE,
    map_adt_a05_identifiers,
    map_adt_a40_identifiers,
    map_adt_a40_merge_identifiers,
    map_trrr_identifiers,
)

# ---------------------------------------------------------------------------
# A05 / A31 (fixed WLIMS authority 328) - existing behaviour
# ---------------------------------------------------------------------------

VALID_ADT_A05 = (
    "MSH|^~\\&|LIMS|LIMS|TRRR|TRRR|20250101010101||ADT^A31^ADT_A05|MSG123|P|2.5\r"
    "PID|1||ABC123^^^328^PI~9876543210^^^NHS^NH||Doe^John^^^||19900101|M\r"
)


def test_map_adt_a05_identifiers_successfully() -> None:
    mapped = map_adt_a05_identifiers(VALID_ADT_A05)

    assert mapped["LIMSIdentifier"] == "ABC123"
    assert mapped["NewIdentifier"] == "9876543210"
    assert mapped["NewIdentifierAssigningAuthority"] == "NHS"
    assert "OldIdentifier" not in mapped
    assert "OldIdentifierAssigningAuthority" not in mapped


def test_map_adt_a05_identifiers_preserves_leading_zeroes_and_text_type() -> None:
    message = (
        "MSH|^~\\&|LIMS|LIMS|TRRR|TRRR|20250101010101||ADT^A31^ADT_A05|MSG123|P|2.5\r"
        "PID|1||001234567^^^328^PI~0001234567^^^NHS^NH||Doe^John^^^||19900101|M\r"
    )

    mapped = map_adt_a05_identifiers(message)

    assert mapped["LIMSIdentifier"] == "001234567"
    assert mapped["NewIdentifier"] == "0001234567"
    assert isinstance(mapped["LIMSIdentifier"], str)
    assert isinstance(mapped["NewIdentifier"], str)


def test_map_adt_a05_identifiers_rejects_missing_lims_identifier() -> None:
    message = (
        "MSH|^~\\&|LIMS|LIMS|TRRR|TRRR|20250101010101||ADT^A31^ADT_A05|MSG123|P|2.5\r"
        "PID|1||9876543210^^^NHS^NH||Doe^John^^^||19900101|M\r"
    )

    try:
        map_adt_a05_identifiers(message)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert str(exc) == "Missing LIMS identifier"


def test_map_adt_a05_identifiers_rejects_missing_nhs_identifier() -> None:
    message = (
        "MSH|^~\\&|LIMS|LIMS|TRRR|TRRR|20250101010101||ADT^A31^ADT_A05|MSG123|P|2.5\r"
        "PID|1||ABC123^^^328^PI||Doe^John^^^||19900101|M\r"
    )

    try:
        map_adt_a05_identifiers(message)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert str(exc) == "Missing NHS identifier"


# ---------------------------------------------------------------------------
# A40 (dynamic sending-LIMS authority from MSH-3.1) - XML
# ---------------------------------------------------------------------------

VALID_ADT_A40_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<ADT_A39 xmlns="urn:hl7-org:v2xml">'
    "<MSH>"
    "<MSH.3><HD.1>WLIMS</HD.1></MSH.3>"
    "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2><MSG.3>ADT_A39</MSG.3></MSH.9>"
    "<MSH.10>CTRL-1</MSH.10>"
    "</MSH>"
    "<PID>"
    "<PID.3><CX.1>LIMS-77</CX.1><CX.4><HD.1>WLIMS</HD.1></CX.4></PID.3>"
    "<PID.3><CX.1>9876543210</CX.1><CX.4><HD.1>NHS</HD.1></CX.4></PID.3>"
    "</PID>"
    "</ADT_A39>"
)


def test_map_adt_a40_xml_successfully() -> None:
    mapped = map_adt_a40_identifiers(VALID_ADT_A40_XML)

    assert mapped["LIMSIdentifier"] == "LIMS-77"
    assert mapped["NewIdentifier"] == "9876543210"
    assert mapped["NewIdentifierAssigningAuthority"] == "NHS"


def test_map_adt_a40_xml_request_has_exactly_three_keys_and_no_old_identifier() -> None:
    mapped = map_adt_a40_identifiers(VALID_ADT_A40_XML)

    assert set(mapped.keys()) == {
        "LIMSIdentifier",
        "NewIdentifier",
        "NewIdentifierAssigningAuthority",
    }
    assert "OldIdentifier" not in mapped
    assert "OldIdentifierAssigningAuthority" not in mapped


def test_map_adt_a40_selects_lims_by_matching_msh3_among_multiple_authorities() -> None:
    message = (
        '<ADT_A39 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.3><HD.1>CHEMO</HD.1></MSH.3>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2></MSH.9>"
        "</MSH>"
        "<PID>"
        "<PID.3><CX.1>WLIMS-ID</CX.1><CX.4><HD.1>WLIMS</HD.1></CX.4></PID.3>"
        "<PID.3><CX.1>CHEMO-ID</CX.1><CX.4><HD.1>CHEMO</HD.1></CX.4></PID.3>"
        "<PID.3><CX.1>9999999999</CX.1><CX.4><HD.1>NHS</HD.1></CX.4></PID.3>"
        "</PID>"
        "</ADT_A39>"
    )

    mapped = map_adt_a40_identifiers(message)

    # Only the repetition whose authority equals MSH-3.1 (CHEMO) is selected as the LIMS id.
    assert mapped["LIMSIdentifier"] == "CHEMO-ID"
    assert mapped["NewIdentifier"] == "9999999999"


def test_map_adt_a40_xml_preserves_leading_zeroes_as_text() -> None:
    message = (
        '<ADT_A39 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.3><HD.1>WLIMS</HD.1></MSH.3>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2></MSH.9>"
        "</MSH>"
        "<PID>"
        "<PID.3><CX.1>000777</CX.1><CX.4><HD.1>WLIMS</HD.1></CX.4></PID.3>"
        "<PID.3><CX.1>0001234567</CX.1><CX.4><HD.1>NHS</HD.1></CX.4></PID.3>"
        "</PID>"
        "</ADT_A39>"
    )

    mapped = map_adt_a40_identifiers(message)

    assert mapped["LIMSIdentifier"] == "000777"
    assert mapped["NewIdentifier"] == "0001234567"
    assert isinstance(mapped["LIMSIdentifier"], str)
    assert isinstance(mapped["NewIdentifier"], str)


def test_map_adt_a40_rejects_missing_sending_lims_authority() -> None:
    message = (
        '<ADT_A39 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.3></MSH.3>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2></MSH.9>"
        "</MSH>"
        "<PID>"
        "<PID.3><CX.1>LIMS-77</CX.1><CX.4><HD.1>WLIMS</HD.1></CX.4></PID.3>"
        "<PID.3><CX.1>9876543210</CX.1><CX.4><HD.1>NHS</HD.1></CX.4></PID.3>"
        "</PID>"
        "</ADT_A39>"
    )

    try:
        map_adt_a40_identifiers(message)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert str(exc) == "Missing sending LIMS authority"


def test_map_adt_a40_rejects_no_pid3_match_for_sending_authority() -> None:
    message = (
        '<ADT_A39 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.3><HD.1>WLIMS</HD.1></MSH.3>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2></MSH.9>"
        "</MSH>"
        "<PID>"
        "<PID.3><CX.1>OTHER-ID</CX.1><CX.4><HD.1>CHEMO</HD.1></CX.4></PID.3>"
        "<PID.3><CX.1>9876543210</CX.1><CX.4><HD.1>NHS</HD.1></CX.4></PID.3>"
        "</PID>"
        "</ADT_A39>"
    )

    try:
        map_adt_a40_identifiers(message)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert str(exc) == "Missing LIMS identifier"


def test_map_adt_a40_rejects_missing_nhs_identifier() -> None:
    message = (
        '<ADT_A39 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.3><HD.1>WLIMS</HD.1></MSH.3>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2></MSH.9>"
        "</MSH>"
        "<PID>"
        "<PID.3><CX.1>LIMS-77</CX.1><CX.4><HD.1>WLIMS</HD.1></CX.4></PID.3>"
        "</PID>"
        "</ADT_A39>"
    )

    try:
        map_adt_a40_identifiers(message)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert str(exc) == "Missing NHS identifier"


def test_map_adt_a40_er7_successfully() -> None:
    message = (
        "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG999|P|2.5\r"
        "PID|1||LIMS-77^^^WLIMS^PI~9876543210^^^NHS^NH||Doe^John^^^||19900101|M\r"
    )

    mapped = map_adt_a40_identifiers(message)

    assert mapped["LIMSIdentifier"] == "LIMS-77"
    assert mapped["NewIdentifier"] == "9876543210"
    assert mapped["NewIdentifierAssigningAuthority"] == "NHS"


# ---------------------------------------------------------------------------
# Dispatcher routing - map_trrr_identifiers on MSH-9.2
# ---------------------------------------------------------------------------


def test_dispatch_a40_uses_dynamic_sending_authority() -> None:
    # MSH-3.1 is CHEMO, so the CHEMO repetition (not 328) must be chosen.
    message = (
        "MSH|^~\\&|CHEMO|CHEMO|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG999|P|2.5\r"
        "PID|1||FIXED-328^^^328^PI~CHEMO-ID^^^CHEMO^PI~9876543210^^^NHS^NH||Doe^John||19900101|M\r"
    )

    mapped = map_trrr_identifiers(message)

    assert mapped["LIMSIdentifier"] == "CHEMO-ID"
    assert mapped["NewIdentifier"] == "9876543210"


def test_dispatch_a31_uses_fixed_328_authority() -> None:
    # MSH-3.1 is LIMS but trigger A31 must force the fixed 328 rule.
    mapped = map_trrr_identifiers(VALID_ADT_A05)

    assert mapped["LIMSIdentifier"] == "ABC123"
    assert mapped["NewIdentifier"] == "9876543210"


def test_dispatch_a31_xml_uses_fixed_328_authority() -> None:
    message = (
        '<ADT_A05 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.3><HD.1>LIMS</HD.1></MSH.3>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A31</MSG.2></MSH.9>"
        "</MSH>"
        "<PID>"
        "<PID.3><CX.1>FIXED-328</CX.1><CX.4><HD.1>328</HD.1></CX.4></PID.3>"
        "<PID.3><CX.1>9876543210</CX.1><CX.4><HD.1>NHS</HD.1></CX.4></PID.3>"
        "</PID>"
        "</ADT_A05>"
    )

    mapped = map_trrr_identifiers(message)

    assert mapped["LIMSIdentifier"] == "FIXED-328"
    assert mapped["NewIdentifier"] == "9876543210"


def test_dispatch_rejects_unsupported_trigger() -> None:
    message = (
        "MSH|^~\\&|LIMS|LIMS|TRRR|TRRR|20250101010101||ADT^A08^ADT_A08|MSG123|P|2.5\r"
        "PID|1||ABC123^^^328^PI~9876543210^^^NHS^NH||Doe^John||19900101|M\r"
    )

    try:
        map_trrr_identifiers(message)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert str(exc).startswith("Unsupported trigger event")


def test_dispatch_rejects_empty_message() -> None:
    try:
        map_trrr_identifiers("   ")
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert str(exc) == "Empty message body"


# ---------------------------------------------------------------------------
# A40 patient merge (MRG-1 old identifier, matching PID-3 new identifier)
# ---------------------------------------------------------------------------


def _merge_xml(mrg: str, pid3: str) -> str:
    return (
        '<ADT_A39 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.3><HD.1>WLIMS</HD.1></MSH.3>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A40</MSG.2><MSG.3>ADT_A39</MSG.3></MSH.9>"
        "</MSH>"
        "<ADT_A39.PATIENT>"
        f"<PID>{pid3}</PID>"
        f"<MRG>{mrg}</MRG>"
        "</ADT_A39.PATIENT>"
        "</ADT_A39>"
    )


def _cx(value: str, authority: str) -> str:
    return f"<CX.1>{value}</CX.1><CX.4><HD.1>{authority}</HD.1></CX.4>"


VALID_MERGE_XML = _merge_xml(
    mrg=f"<MRG.1>{_cx('OLD-001', 'NHS')}</MRG.1>",
    pid3=f"<PID.3>{_cx('LIMS-77', 'WLIMS')}</PID.3><PID.3>{_cx('NEW-002', 'NHS')}</PID.3>",
)

MERGE_KEYS = {
    "OldIdentifier",
    "OldIdentifierAssigningAuthority",
    "NewIdentifier",
    "NewIdentifierAssigningAuthority",
}


def _assert_value_error(func, message: str, expected: str) -> None:  # type: ignore[no-untyped-def]
    try:
        func(message)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert str(exc) == expected


def test_map_a40_merge_xml_successfully() -> None:
    mapped = map_adt_a40_merge_identifiers(VALID_MERGE_XML)

    assert mapped == {
        "OldIdentifier": "OLD-001",
        "OldIdentifierAssigningAuthority": "NHS",
        "NewIdentifier": "NEW-002",
        "NewIdentifierAssigningAuthority": "NHS",
    }


def test_map_a40_merge_request_has_no_lims_identifier() -> None:
    mapped = map_adt_a40_merge_identifiers(VALID_MERGE_XML)

    assert set(mapped.keys()) == MERGE_KEYS
    assert "LIMSIdentifier" not in mapped


def test_map_a40_merge_selects_new_identifier_by_matching_authority() -> None:
    message = _merge_xml(
        mrg=f"<MRG.1>{_cx('OLD-001', 'CHEMO')}</MRG.1>",
        pid3=(
            f"<PID.3>{_cx('WLIMS-ID', 'WLIMS')}</PID.3>"
            f"<PID.3>{_cx('NHS-ID', 'NHS')}</PID.3>"
            f"<PID.3>{_cx('CHEMO-NEW', 'CHEMO')}</PID.3>"
        ),
    )

    mapped = map_adt_a40_merge_identifiers(message)

    assert mapped["NewIdentifier"] == "CHEMO-NEW"
    assert mapped["NewIdentifierAssigningAuthority"] == "CHEMO"
    assert mapped["OldIdentifierAssigningAuthority"] == "CHEMO"


def test_map_a40_merge_preserves_leading_zeroes_as_text() -> None:
    message = _merge_xml(
        mrg=f"<MRG.1>{_cx('0001234567', 'NHS')}</MRG.1>",
        pid3=f"<PID.3>{_cx('0009876543', 'NHS')}</PID.3>",
    )

    mapped = map_adt_a40_merge_identifiers(message)

    assert mapped["OldIdentifier"] == "0001234567"
    assert mapped["NewIdentifier"] == "0009876543"
    assert isinstance(mapped["OldIdentifier"], str)
    assert isinstance(mapped["NewIdentifier"], str)


def test_map_a40_merge_rejects_missing_old_identifier() -> None:
    message = _merge_xml(
        mrg="<MRG.1><CX.1></CX.1><CX.4><HD.1>NHS</HD.1></CX.4></MRG.1>",
        pid3=f"<PID.3>{_cx('NEW-002', 'NHS')}</PID.3>",
    )

    _assert_value_error(map_adt_a40_merge_identifiers, message, "Missing old identifier")


def test_map_a40_merge_rejects_missing_mrg_segment_as_missing_old_identifier() -> None:
    message = (
        "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG1|P|2.5\r"
        "PID|1||NEW-002^^^NHS^NH\r"
    )

    _assert_value_error(map_adt_a40_merge_identifiers, message, "Missing old identifier")


def test_map_a40_merge_rejects_missing_old_assigning_authority() -> None:
    message = _merge_xml(
        mrg="<MRG.1><CX.1>OLD-001</CX.1></MRG.1>",
        pid3=f"<PID.3>{_cx('NEW-002', 'NHS')}</PID.3>",
    )

    _assert_value_error(map_adt_a40_merge_identifiers, message, "Missing old assigning authority")


def test_map_a40_merge_rejects_missing_new_identifier() -> None:
    message = _merge_xml(
        mrg=f"<MRG.1>{_cx('OLD-001', 'NHS')}</MRG.1>",
        pid3=f"<PID.3>{_cx('LIMS-77', 'WLIMS')}</PID.3>",
    )

    _assert_value_error(map_adt_a40_merge_identifiers, message, "Missing new identifier")


def test_map_a40_merge_er7_successfully() -> None:
    message = (
        "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG1|P|2.5\r"
        "PID|1||LIMS-77^^^WLIMS^PI~0009876543^^^NHS^NH||Doe^John\r"
        "MRG|0001234567^^^NHS^NH\r"
    )

    mapped = map_adt_a40_merge_identifiers(message)

    assert mapped == {
        "OldIdentifier": "0001234567",
        "OldIdentifierAssigningAuthority": "NHS",
        "NewIdentifier": "0009876543",
        "NewIdentifierAssigningAuthority": "NHS",
    }


def test_merge_mapping_type_maps_a40_to_merge_payload() -> None:
    mapped = map_trrr_identifiers(VALID_MERGE_XML, MAPPING_MERGE)

    assert set(mapped.keys()) == MERGE_KEYS


def test_nhs_id_update_mapping_type_ignores_mrg_on_a40() -> None:
    # A real ADT_A39 always carries MRG; the NHS-ID-update mapping must not treat it as a merge.
    mapped = map_trrr_identifiers(VALID_MERGE_XML, MAPPING_NHS_ID_UPDATE)

    assert mapped == {
        "LIMSIdentifier": "LIMS-77",
        "NewIdentifier": "NEW-002",
        "NewIdentifierAssigningAuthority": "NHS",
    }


def test_a40_meeting_both_criteria_yields_two_distinct_mappings() -> None:
    update = map_trrr_identifiers(VALID_MERGE_XML, MAPPING_NHS_ID_UPDATE)
    merge = map_trrr_identifiers(VALID_MERGE_XML, MAPPING_MERGE)

    assert "OldIdentifier" not in update
    assert set(merge.keys()) == MERGE_KEYS


def test_default_mapping_type_is_nhs_id_update() -> None:
    mapped = map_trrr_identifiers(VALID_ADT_A40_XML)

    assert "OldIdentifier" not in mapped
    assert mapped["LIMSIdentifier"] == "LIMS-77"


def test_merge_mapping_type_rejects_a40_without_mrg() -> None:
    _assert_value_error(
        lambda m: map_trrr_identifiers(m, MAPPING_MERGE), VALID_ADT_A40_XML, "Missing old identifier"
    )


def test_merge_mapping_type_rejects_non_a40_trigger() -> None:
    _assert_value_error(
        lambda m: map_trrr_identifiers(m, MAPPING_MERGE), VALID_ADT_A05, "Unsupported trigger event: A31"
    )


def test_unknown_mapping_type_is_rejected() -> None:
    _assert_value_error(
        lambda m: map_trrr_identifiers(m, "BOGUS"), VALID_MERGE_XML, "Unsupported mapping type: BOGUS"
    )

def test_nhs_id_update_fails_when_a40_has_no_nhs_identifier() -> None:
    message = (
        "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG1|P|2.5\r"
        "PID|1||LIMS-77^^^WLIMS^PI||Doe^John\r"
        "MRG|OLD-001^^^WLIMS^PI\r"
    )

    _assert_value_error(lambda m: map_trrr_identifiers(m, MAPPING_NHS_ID_UPDATE), message, "Missing NHS identifier")

    # The same A40 is still valid for the merge mapping (every A40), so it is mapped there.
    assert map_trrr_identifiers(message, MAPPING_MERGE)["OldIdentifier"] == "OLD-001"


def test_nhs_id_update_fails_when_lims_authority_missing_from_pid3() -> None:
    message = (
        "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG1|P|2.5\r"
        "PID|1||9876543210^^^NHS^NH||Doe^John\r"
    )

    _assert_value_error(lambda m: map_trrr_identifiers(m, MAPPING_NHS_ID_UPDATE), message, "Missing LIMS identifier")


def test_unsupported_trigger_fails_in_both_mapping_types() -> None:
    message = (
        "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A08^ADT_A08|MSG1|P|2.5\r"
        "PID|1||LIMS-77^^^WLIMS^PI~9876543210^^^NHS^NH||Doe^John\r"
    )

    for mapping_type in (MAPPING_NHS_ID_UPDATE, MAPPING_MERGE):
        _assert_value_error(
            lambda m, mt=mapping_type: map_trrr_identifiers(m, mt), message, "Unsupported trigger event: A08"
        )


def test_missing_sending_authority_and_missing_mrg_fail_with_their_own_reason() -> None:
    no_authority = (
        "MSH|^~\\&||WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG1|P|2.5\r"
        "PID|1||LIMS-77^^^WLIMS^PI~9876543210^^^NHS^NH||Doe^John\r"
    )
    _assert_value_error(
        lambda m: map_trrr_identifiers(m, MAPPING_NHS_ID_UPDATE), no_authority, "Missing sending LIMS authority"
    )
    _assert_value_error(
        lambda m: map_trrr_identifiers(m, MAPPING_MERGE), VALID_ADT_A40_XML, "Missing old identifier"
    )


def test_a05_trigger_is_unsupported() -> None:
    message = (
        "MSH|^~\\&|LIMS|LIMS|TRRR|TRRR|20250101010101||ADT^A05^ADT_A05|MSG123|P|2.5\r"
        "PID|1||ABC123^^^328^PI~9876543210^^^NHS^NH||Doe^John||19900101|M\r"
    )

    _assert_value_error(
        lambda m: map_trrr_identifiers(m, MAPPING_NHS_ID_UPDATE), message, "Unsupported trigger event: A05"
    )
