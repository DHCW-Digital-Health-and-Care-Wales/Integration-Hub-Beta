from __future__ import annotations

from db_sender_trrr.identifier_mapper import (
    map_adt_a05_identifiers,
    map_adt_a40_identifiers,
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


def test_dispatch_a05_xml_uses_fixed_328_authority() -> None:
    message = (
        '<ADT_A05 xmlns="urn:hl7-org:v2xml">'
        "<MSH>"
        "<MSH.3><HD.1>LIMS</HD.1></MSH.3>"
        "<MSH.9><MSG.1>ADT</MSG.1><MSG.2>A05</MSG.2></MSH.9>"
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
