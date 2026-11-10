from __future__ import annotations

from unittest.mock import MagicMock, patch

from message_bus_lib.dead_letter import DeadLetterMessage

from db_sender_trrr import application
from db_sender_trrr.identifier_mapper import MAPPING_MERGE, MAPPING_NHS_ID_UPDATE

A40_WITH_NHS = (
    "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG1|P|2.5\r"
    "PID|1||LIMS-77^^^WLIMS^PI~9876543210^^^NHS^NH||Doe^John\r"
    "MRG|OLD-001^^^WLIMS^PI\r"
)
A40_WITHOUT_NHS = (
    "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG2|P|2.5\r"
    "PID|1||LIMS-77^^^WLIMS^PI||Doe^John\r"
    "MRG|OLD-001^^^WLIMS^PI\r"
)
A40_WITHOUT_MRG = (
    "MSH|^~\\&|WLIMS|WLIMS|TRRR|TRRR|20250101010101||ADT^A40^ADT_A39|MSG3|P|2.5\r"
    "PID|1||LIMS-77^^^WLIMS^PI~9876543210^^^NHS^NH||Doe^John\r"
)


def _run(body: str, mapping_type: str) -> tuple[bool, MagicMock]:
    message = MagicMock()
    message.body = [body.encode("utf-8")]
    db_client = MagicMock()
    app_config = MagicMock()
    app_config.mapping_type = mapping_type
    app_config.db_stored_procedure = "dbo.Test"

    with (
        patch.object(application, "extract_metadata", return_value=MagicMock()),
        patch.object(
            application,
            "get_metadata_log_values",
            return_value={"correlation_id": "c1", "workflow_id": "w1"},
        ),
        patch.object(application, "correlation_id_for_logger", return_value=None),
    ):
        result = application.process_message(message, db_client, app_config, MagicMock(), MagicMock())
    return result, db_client


def test_nhs_id_update_writes_when_a40_meets_criteria() -> None:
    result, db_client = _run(A40_WITH_NHS, MAPPING_NHS_ID_UPDATE)

    assert result is True
    db_client.execute_identifier_update.assert_called_once()


def test_nhs_id_update_skips_a40_without_nhs_identifier_without_db_call() -> None:
    result, db_client = _run(A40_WITHOUT_NHS, MAPPING_NHS_ID_UPDATE)

    assert result is True
    db_client.execute_identifier_update.assert_not_called()


def test_merge_still_writes_the_a40_that_nhs_id_update_skipped() -> None:
    result, db_client = _run(A40_WITHOUT_NHS, MAPPING_MERGE)

    assert result is True
    db_client.execute_identifier_update.assert_called_once()


def test_merge_dead_letters_a40_without_mrg() -> None:
    try:
        _run(A40_WITHOUT_MRG, MAPPING_MERGE)
        raise AssertionError("Expected DeadLetterMessage")
    except DeadLetterMessage as exc:
        assert exc.description == "Missing old identifier"
