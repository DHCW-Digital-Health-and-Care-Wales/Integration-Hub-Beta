"""Unit tests for dashboard.services.flow_sources.

Cosmos calls are mocked throughout — no real Cosmos access is required.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from dashboard.services import flow_sources


@pytest.fixture(autouse=True)
def _configured_persistence() -> Generator[None, None, None]:
    with patch.object(flow_sources.cosmos_store, "is_configured", return_value=True):
        yield


# ---------------------------------------------------------------------------
# add_source / update_source / delete_source
# ---------------------------------------------------------------------------


class TestAddSource:
    def test_persists_and_returns_source_with_generated_id(self) -> None:
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=[]),
            patch.object(flow_sources.cosmos_store, "create_document", return_value=True) as create,
        ):
            source = flow_sources.add_source("PHW HL7 Server", "phw.example.nhs.uk", "2575")

        assert source["description"] == "PHW HL7 Server"
        assert source["url"] == "phw.example.nhs.uk"
        assert source["port"] == 2575
        assert source["id"]
        create.assert_called_once_with(
            "flow-source-server",
            "flow-source:phw.example.nhs.uk:2575",
            {**source, "source_id": source["id"], "storage_id": "flow-source:phw.example.nhs.uk:2575"},
            doc_type="flow_source_server",
        )

    def test_strips_description_whitespace(self) -> None:
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=[]),
            patch.object(flow_sources.cosmos_store, "create_document", return_value=True),
        ):
            source = flow_sources.add_source("  PHW  ", "phw.example.nhs.uk", 2575)
        assert source["description"] == "PHW"

    def test_rejects_empty_description(self) -> None:
        with pytest.raises(flow_sources.InvalidSourceError):
            flow_sources.add_source("", "phw.example.nhs.uk", 2575)

    def test_rejects_description_too_long(self) -> None:
        with pytest.raises(flow_sources.InvalidSourceError):
            flow_sources.add_source("a" * 201, "phw.example.nhs.uk", 2575)

    def test_rejects_invalid_url(self) -> None:
        with pytest.raises(flow_sources.InvalidSourceError):
            flow_sources.add_source("PHW", "not a valid host!", 2575)

    def test_rejects_invalid_port(self) -> None:
        with pytest.raises(flow_sources.InvalidSourceError):
            flow_sources.add_source("PHW", "phw.example.nhs.uk", 999999)

    def test_rejects_duplicate_url_and_port(self) -> None:
        existing = [{"source_id": "1", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(
                flow_sources.cosmos_store,
                "create_document",
                side_effect=flow_sources.CosmosResourceExistsError(message="duplicate"),
            ) as create,
            pytest.raises(flow_sources.InvalidSourceError),
        ):
            flow_sources.add_source("PHW again", "phw.example.nhs.uk", 2575)
        create.assert_called_once()

    def test_duplicate_check_is_case_insensitive_on_url(self) -> None:
        existing = [{"source_id": "1", "description": "PHW", "url": "PHW.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(
                flow_sources.cosmos_store,
                "create_document",
                side_effect=flow_sources.CosmosResourceExistsError(message="duplicate"),
            ),
            pytest.raises(flow_sources.InvalidSourceError),
        ):
            flow_sources.add_source("PHW again", "phw.example.nhs.uk", 2575)

    def test_allows_same_url_with_different_port(self) -> None:
        existing = [{"source_id": "1", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(flow_sources.cosmos_store, "create_document", return_value=True),
        ):
            source = flow_sources.add_source("PHW alt port", "phw.example.nhs.uk", 2576)
        assert source["port"] == 2576

    def test_raises_persistence_error_when_create_fails(self) -> None:
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=[]),
            patch.object(flow_sources.cosmos_store, "create_document", return_value=False),
            pytest.raises(flow_sources.SourcePersistenceError),
        ):
            flow_sources.add_source("PHW", "phw.example.nhs.uk", 2575)


class TestUpdateSource:
    def test_persists_with_supplied_id(self) -> None:
        existing = [{"source_id": "abc-123", "description": "Old PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(flow_sources.cosmos_store, "upsert_document", return_value=True) as upsert,
        ):
            source = flow_sources.update_source("abc-123", "PHW", "phw.example.nhs.uk", 2575)

        assert source["id"] == "abc-123"
        upsert.assert_called_once_with(
            "flow-source-server",
            "abc-123",
            {**source, "source_id": "abc-123", "storage_id": "abc-123"},
            doc_type="flow_source_server",
        )

    def test_rejects_invalid_fields(self) -> None:
        with pytest.raises(flow_sources.InvalidSourceError):
            flow_sources.update_source("abc-123", "", "phw.example.nhs.uk", 2575)

    def test_rejects_updating_unknown_source(self) -> None:
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=[]),
            pytest.raises(flow_sources.InvalidSourceError, match="Source not found."),
        ):
            flow_sources.update_source("missing", "PHW", "phw.example.nhs.uk", 2575)

    def test_allows_saving_unchanged_url_and_port_on_itself(self) -> None:
        existing = [{"source_id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(flow_sources.cosmos_store, "upsert_document", return_value=True),
        ):
            source = flow_sources.update_source("abc-123", "PHW renamed", "phw.example.nhs.uk", 2575)
        assert source["description"] == "PHW renamed"

    def test_rejects_url_and_port_matching_a_different_source(self) -> None:
        existing = [
            {"source_id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575},
            {"source_id": "other-456", "description": "Paris", "url": "paris.example.nhs.uk", "port": 2577},
        ]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(
                flow_sources.cosmos_store,
                "create_document",
                side_effect=flow_sources.CosmosResourceExistsError(message="duplicate"),
            ) as create,
            pytest.raises(flow_sources.InvalidSourceError),
        ):
            flow_sources.update_source("abc-123", "PHW", "paris.example.nhs.uk", 2577)
        create.assert_called_once()

    def test_moves_document_to_new_storage_id_when_endpoint_changes(self) -> None:
        existing = [{"source_id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(flow_sources.cosmos_store, "create_document", return_value=True) as create,
            patch.object(flow_sources.cosmos_store, "delete_document", return_value=True) as delete,
        ):
            source = flow_sources.update_source("abc-123", "PHW", "paris.example.nhs.uk", 2577)

        assert source == {"id": "abc-123", "description": "PHW", "url": "paris.example.nhs.uk", "port": 2577}
        create.assert_called_once_with(
            "flow-source-server",
            "flow-source:paris.example.nhs.uk:2577",
            {
                "description": "PHW",
                "url": "paris.example.nhs.uk",
                "port": 2577,
                "id": "abc-123",
                "source_id": "abc-123",
                "storage_id": "flow-source:paris.example.nhs.uk:2577",
            },
            doc_type="flow_source_server",
        )
        delete.assert_called_once_with("flow-source-server", "abc-123")

    def test_rolls_back_new_document_when_old_document_delete_fails(self) -> None:
        existing = [{"source_id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(flow_sources.cosmos_store, "create_document", return_value=True),
            patch.object(flow_sources.cosmos_store, "delete_document", side_effect=[False, True]) as delete,
            pytest.raises(flow_sources.SourcePersistenceError),
        ):
            flow_sources.update_source("abc-123", "PHW", "paris.example.nhs.uk", 2577)

        assert delete.call_args_list == [
            (("flow-source-server", "abc-123"), {}),
            (("flow-source-server", "flow-source:paris.example.nhs.uk:2577"), {}),
        ]

    def test_raises_persistence_error_when_update_write_fails(self) -> None:
        existing = [{"source_id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(flow_sources.cosmos_store, "upsert_document", return_value=False),
            pytest.raises(flow_sources.SourcePersistenceError),
        ):
            flow_sources.update_source("abc-123", "PHW renamed", "phw.example.nhs.uk", 2575)


class TestDeleteSource:
    def test_delegates_to_cosmos_store(self) -> None:
        existing = [{"source_id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(flow_sources.cosmos_store, "delete_document", return_value=True) as delete_document,
        ):
            flow_sources.delete_source("abc-123")
        delete_document.assert_called_once_with("flow-source-server", "abc-123")

    def test_missing_source_is_a_noop(self) -> None:
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=[]),
            patch.object(flow_sources.cosmos_store, "delete_document") as delete_document,
        ):
            flow_sources.delete_source("missing")

        delete_document.assert_not_called()

    def test_raises_persistence_error_when_delete_fails(self) -> None:
        existing = [{"source_id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(flow_sources.cosmos_store, "delete_document", return_value=False),
            pytest.raises(flow_sources.SourcePersistenceError),
        ):
            flow_sources.delete_source("abc-123")


class TestListSources:
    def test_returns_sorted_by_description(self) -> None:
        documents = [
            {"source_id": "2", "description": "Zeta", "url": "z.example.com", "port": 443},
            {"source_id": "1", "description": "alpha", "url": "a.example.com", "port": 22},
        ]
        with patch.object(flow_sources.cosmos_store, "query_documents", return_value=documents):
            sources = flow_sources.list_sources()

        assert [s["description"] for s in sources] == ["alpha", "Zeta"]

    def test_remaps_source_id_to_id(self) -> None:
        """Regression test: cosmos_store strips "id" as routing metadata, so the
        document's real identifier must round-trip via the "source_id" field —
        otherwise edit/delete break because the frontend never gets a usable id.
        """
        documents = [{"source_id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with patch.object(flow_sources.cosmos_store, "query_documents", return_value=documents):
            sources = flow_sources.list_sources()

        assert sources == [{"id": "abc-123", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]

    def test_hides_internal_storage_id(self) -> None:
        documents = [
            {
                "source_id": "abc-123",
                "storage_id": "flow-source:phw.example.nhs.uk:2575",
                "description": "PHW",
                "url": "phw.example.nhs.uk",
                "port": 2575,
            }
        ]
        with patch.object(flow_sources.cosmos_store, "query_documents", return_value=documents):
            sources = flow_sources.list_sources()

        assert "_storage_id" not in sources[0]
        assert "storage_id" not in sources[0]


class TestListSourcesAsEndpointOptions:
    def test_builds_label_host_port_options(self) -> None:
        documents = [{"source_id": "1", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with patch.object(flow_sources.cosmos_store, "query_documents", return_value=documents):
            options = flow_sources.list_sources_as_endpoint_options()

        assert options == [{"label": "PHW (phw.example.nhs.uk:2575)", "host": "phw.example.nhs.uk", "port": 2575}]

    def test_returns_empty_list_when_no_sources(self) -> None:
        with patch.object(flow_sources.cosmos_store, "query_documents", return_value=[]):
            assert flow_sources.list_sources_as_endpoint_options() == []


# ---------------------------------------------------------------------------
# parse_csv / import_sources
# ---------------------------------------------------------------------------


class TestParseCsv:
    def test_parses_valid_rows(self) -> None:
        csv_text = "description,url,port\nPHW,phw.example.nhs.uk,2575\nParis,paris.example.nhs.uk,2577\n"
        rows, errors = flow_sources.parse_csv(csv_text)

        assert errors == []
        assert rows == [
            {"description": "PHW", "url": "phw.example.nhs.uk", "port": 2575},
            {"description": "Paris", "url": "paris.example.nhs.uk", "port": 2577},
        ]

    def test_header_matched_case_insensitively_and_any_order(self) -> None:
        csv_text = "Port,Description,URL\n2575,PHW,phw.example.nhs.uk\n"
        rows, errors = flow_sources.parse_csv(csv_text)

        assert errors == []
        assert rows == [{"description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]

    def test_skips_invalid_rows_but_keeps_valid_ones(self) -> None:
        csv_text = "description,url,port\nPHW,phw.example.nhs.uk,2575\nBad,,not-a-port\n"
        rows, errors = flow_sources.parse_csv(csv_text)

        assert rows == [{"description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        assert len(errors) == 1
        assert "Row 3" in errors[0]

    def test_empty_file_returns_error(self) -> None:
        rows, errors = flow_sources.parse_csv("")
        assert rows == []
        assert errors == ["CSV file is empty."]

    def test_missing_required_column_returns_error(self) -> None:
        rows, errors = flow_sources.parse_csv("description,url\nPHW,phw.example.nhs.uk\n")
        assert rows == []
        assert "port" in errors[0]

    def test_flags_duplicate_rows_within_the_same_file(self) -> None:
        csv_text = (
            "description,url,port\n"
            "PHW,phw.example.nhs.uk,2575\n"
            "PHW dupe,PHW.example.nhs.uk,2575\n"
        )
        rows, errors = flow_sources.parse_csv(csv_text)

        assert rows == [{"description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        assert len(errors) == 1
        assert "Row 3" in errors[0] and "row 2" in errors[0]


class TestImportSources:
    def test_imports_valid_rows_and_reports_errors(self) -> None:
        csv_text = "description,url,port\nPHW,phw.example.nhs.uk,2575\nBad,,not-a-port\n"
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=[]),
            patch.object(flow_sources.cosmos_store, "create_document", return_value=True) as create,
        ):
            result = flow_sources.import_sources(csv_text)

        assert result == {
            "imported": 1,
            "errors": ["Row 3: Host must not be empty"],
            "persistence_failed": False,
        }
        create.assert_called_once()
        persisted_doc = create.call_args.args[2]
        assert persisted_doc["source_id"] == persisted_doc["id"]

    def test_skips_rows_matching_an_already_stored_source(self) -> None:
        csv_text = "description,url,port\nPHW,phw.example.nhs.uk,2575\nParis,paris.example.nhs.uk,2577\n"
        existing = [{"source_id": "1", "description": "PHW", "url": "phw.example.nhs.uk", "port": 2575}]
        with (
            patch.object(flow_sources.cosmos_store, "query_documents", return_value=existing),
            patch.object(
                flow_sources.cosmos_store,
                "create_document",
                side_effect=[flow_sources.CosmosResourceExistsError(message="duplicate"), True],
            ) as create,
        ):
            result = flow_sources.import_sources(csv_text)

        assert result["imported"] == 1
        assert result["persistence_failed"] is False
        assert len(result["errors"]) == 1
        assert "already exists" in result["errors"][0]
        persisted_doc = create.call_args.args[2]
        assert persisted_doc["url"] == "paris.example.nhs.uk"

    def test_reports_persistence_error_when_disabled(self) -> None:
        csv_text = "description,url,port\nPHW,phw.example.nhs.uk,2575\n"
        with patch.object(flow_sources.cosmos_store, "is_configured", return_value=False):
            result = flow_sources.import_sources(csv_text)

        assert result == {
            "imported": 0,
            "errors": ["Source persistence is not configured."],
            "persistence_failed": True,
        }
