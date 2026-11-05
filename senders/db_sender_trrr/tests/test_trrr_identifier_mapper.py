from __future__ import annotations

from db_sender_trrr.identifier_mapper import map_adt_a05_identifiers


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
