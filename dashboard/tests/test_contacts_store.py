"""Unit tests for dashboard.services.contacts_store.

Cosmos calls and flow discovery are mocked throughout — no real Cosmos access or
Azure credentials are required.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from dashboard.services import contacts_store

_FLOWS = {
    "phw-to-mpi": {"id": "phw-to-mpi", "label": "PHW → MPI"},
    "paris-to-mpi": {"id": "paris-to-mpi", "label": "Paris → MPI"},
}


@pytest.fixture(autouse=True)
def _configured_persistence() -> Generator[None, None, None]:
    with (
        patch.object(contacts_store.cosmos_store, "is_configured", return_value=True),
        patch.object(contacts_store, "get_flows", return_value=_FLOWS),
    ):
        yield


def _base_contact(**overrides: object) -> dict:
    data: dict[str, object] = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.nhs.uk",
        "phone_number": "",
        "organisation_type": "Team",
        "organisation_name": "Hub Team",
        "notes": "",
        "flow_ids": ["phw-to-mpi"],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# add_contact
# ---------------------------------------------------------------------------


class TestAddContact:
    def test_persists_and_returns_contact_with_generated_id(self) -> None:
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True) as upsert,
        ):
            contact = contacts_store.add_contact(_base_contact())

        assert contact["first_name"] == "Jane"
        assert contact["last_name"] == "Doe"
        assert contact["email"] == "jane.doe@example.nhs.uk"
        assert contact["deleted"] is False
        assert contact["id"]
        upsert.assert_called_once()
        args, kwargs = upsert.call_args
        assert args[0] == "contacts"
        assert args[1] == contact["id"]
        assert kwargs["doc_type"] == "contact"

    def test_lowercases_email(self) -> None:
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True),
        ):
            contact = contacts_store.add_contact(_base_contact(email="Jane.Doe@Example.NHS.UK"))
        assert contact["email"] == "jane.doe@example.nhs.uk"

    def test_rejects_missing_first_name(self) -> None:
        with pytest.raises(contacts_store.InvalidContactError):
            contacts_store.add_contact(_base_contact(first_name=""))

    def test_rejects_name_too_long(self) -> None:
        with pytest.raises(contacts_store.InvalidContactError):
            contacts_store.add_contact(_base_contact(first_name="a" * 101))

    def test_rejects_missing_email_and_phone(self) -> None:
        with pytest.raises(contacts_store.InvalidContactError, match="email address or a phone number"):
            contacts_store.add_contact(_base_contact(email="", phone_number=""))

    def test_allows_phone_only(self) -> None:
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True),
        ):
            contact = contacts_store.add_contact(_base_contact(email="", phone_number="029 2000 0000"))
        assert contact["phone_number"] == "029 2000 0000"

    def test_rejects_invalid_email(self) -> None:
        with pytest.raises(contacts_store.InvalidContactError):
            contacts_store.add_contact(_base_contact(email="not-an-email"))

    def test_rejects_invalid_phone(self) -> None:
        with pytest.raises(contacts_store.InvalidContactError):
            contacts_store.add_contact(_base_contact(email="", phone_number="call me maybe!!"))

    def test_rejects_invalid_organisation_type(self) -> None:
        with pytest.raises(contacts_store.InvalidContactError, match="Organisation type"):
            contacts_store.add_contact(_base_contact(organisation_type="Hospital"))

    def test_rejects_missing_organisation_name(self) -> None:
        with pytest.raises(contacts_store.InvalidContactError):
            contacts_store.add_contact(_base_contact(organisation_name=""))

    def test_rejects_unknown_flow_id(self) -> None:
        with pytest.raises(contacts_store.InvalidContactError, match="Unknown flow"):
            contacts_store.add_contact(_base_contact(flow_ids=["not-a-real-flow"]))

    def test_accepts_flow_ids_unchecked_when_flow_discovery_unavailable(self) -> None:
        with (
            patch.object(contacts_store, "get_flows", side_effect=RuntimeError("boom")),
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True),
        ):
            contact = contacts_store.add_contact(_base_contact(flow_ids=["whatever-flow"]))
        assert contact["flow_ids"] == ["whatever-flow"]

    def test_raises_persistence_error_when_upsert_fails(self) -> None:
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=False),
            pytest.raises(contacts_store.ContactPersistenceError),
        ):
            contacts_store.add_contact(_base_contact())

    def test_raises_persistence_error_when_not_configured(self) -> None:
        with (
            patch.object(contacts_store.cosmos_store, "is_configured", return_value=False),
            pytest.raises(contacts_store.ContactPersistenceError),
        ):
            contacts_store.add_contact(_base_contact())


# ---------------------------------------------------------------------------
# update_contact / delete_contact
# ---------------------------------------------------------------------------


class TestUpdateContact:
    def test_updates_existing_contact_and_preserves_created_at(self) -> None:
        existing = [
            {
                "contact_id": "abc-123",
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane.doe@example.nhs.uk",
                "phone_number": "",
                "organisation_type": "Team",
                "organisation_name": "Hub Team",
                "notes": "",
                "flow_ids": [],
                "deleted": False,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }
        ]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=existing),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True) as upsert,
        ):
            updated = contacts_store.update_contact("abc-123", _base_contact(last_name="Smith"))

        assert updated["last_name"] == "Smith"
        assert updated["created_at"] == "2024-01-01T00:00:00+00:00"
        assert updated["updated_at"] != "2024-01-01T00:00:00+00:00"
        upsert.assert_called_once()

    def test_rejects_updating_unknown_contact(self) -> None:
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]),
            pytest.raises(contacts_store.InvalidContactError, match="not found"),
        ):
            contacts_store.update_contact("missing-id", _base_contact())


class TestDeleteContact:
    def test_soft_deletes_by_setting_deleted_flag(self) -> None:
        existing = [
            {
                "contact_id": "abc-123",
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane.doe@example.nhs.uk",
                "phone_number": "",
                "organisation_type": "Team",
                "organisation_name": "Hub Team",
                "notes": "",
                "flow_ids": [],
                "deleted": False,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }
        ]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=existing),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True) as upsert,
        ):
            contacts_store.delete_contact("abc-123")

        upsert.assert_called_once()
        persisted_payload = upsert.call_args[0][2]
        assert persisted_payload["deleted"] is True
        assert persisted_payload["deleted_at"]

    def test_is_a_no_op_for_unknown_contact(self) -> None:
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]),
            patch.object(contacts_store.cosmos_store, "upsert_document") as upsert,
        ):
            contacts_store.delete_contact("missing-id")
        upsert.assert_not_called()


class TestRestoreContact:
    def test_clears_deleted_flag_and_deleted_at(self) -> None:
        existing = [
            _stored_full(
                "abc-123",
                deleted=True,
                deleted_at="2024-01-01T00:00:00+00:00",
            )
        ]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=existing),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True) as upsert,
        ):
            restored = contacts_store.restore_contact("abc-123")

        assert restored is not None
        assert restored["deleted"] is False
        assert restored["deleted_at"] is None
        persisted_payload = upsert.call_args[0][2]
        assert persisted_payload["deleted_at"] is None

    def test_returns_none_for_unknown_contact(self) -> None:
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]):
            assert contacts_store.restore_contact("missing-id") is None


# ---------------------------------------------------------------------------
# purge_expired_contacts
# ---------------------------------------------------------------------------


def _stored_full(contact_id: str, **overrides: object) -> dict:
    data: dict[str, object] = {
        "contact_id": contact_id,
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.nhs.uk",
        "phone_number": "",
        "organisation_type": "Team",
        "organisation_name": "Hub Team",
        "notes": "",
        "flow_ids": [],
        "deleted": False,
        "deleted_at": None,
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    data.update(overrides)
    return data


class TestPurgeExpiredContacts:
    def test_purges_contacts_deleted_past_the_retention_window(self) -> None:
        now = datetime(2024, 6, 1, tzinfo=UTC)
        stale_deleted_at = (now - timedelta(days=contacts_store.CONTACT_RETENTION_DAYS + 1)).isoformat()
        stored = [_stored_full("abc-123", deleted=True, deleted_at=stale_deleted_at)]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored),
            patch.object(contacts_store.cosmos_store, "delete_document", return_value=True) as delete,
        ):
            purged = contacts_store.purge_expired_contacts(now=now)

        assert purged == 1
        delete.assert_called_once_with("contacts", "abc-123")

    def test_keeps_contacts_deleted_within_the_retention_window(self) -> None:
        now = datetime(2024, 6, 1, tzinfo=UTC)
        recent_deleted_at = (now - timedelta(days=1)).isoformat()
        stored = [_stored_full("abc-123", deleted=True, deleted_at=recent_deleted_at)]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored),
            patch.object(contacts_store.cosmos_store, "delete_document") as delete,
        ):
            purged = contacts_store.purge_expired_contacts(now=now)

        assert purged == 0
        delete.assert_not_called()

    def test_ignores_non_deleted_contacts(self) -> None:
        stored = [_stored_full("abc-123", deleted=False, deleted_at=None)]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored),
            patch.object(contacts_store.cosmos_store, "delete_document") as delete,
        ):
            purged = contacts_store.purge_expired_contacts()

        assert purged == 0
        delete.assert_not_called()

    def test_falls_back_to_updated_at_when_deleted_at_missing(self) -> None:
        now = datetime(2024, 6, 1, tzinfo=UTC)
        stale = (now - timedelta(days=contacts_store.CONTACT_RETENTION_DAYS + 1)).isoformat()
        stored = [_stored_full("abc-123", deleted=True, deleted_at=None, updated_at=stale)]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored),
            patch.object(contacts_store.cosmos_store, "delete_document", return_value=True) as delete,
        ):
            purged = contacts_store.purge_expired_contacts(now=now)

        assert purged == 1
        delete.assert_called_once_with("contacts", "abc-123")

    def test_skips_contact_with_unparseable_timestamp(self) -> None:
        stored = [_stored_full("abc-123", deleted=True, deleted_at="not-a-date", updated_at="also-not-a-date")]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored),
            patch.object(contacts_store.cosmos_store, "delete_document") as delete,
        ):
            purged = contacts_store.purge_expired_contacts()

        assert purged == 0
        delete.assert_not_called()

    def test_is_a_no_op_when_persistence_not_configured(self) -> None:
        with (
            patch.object(contacts_store.cosmos_store, "is_configured", return_value=False),
            patch.object(contacts_store.cosmos_store, "query_documents") as query,
        ):
            purged = contacts_store.purge_expired_contacts()

        assert purged == 0
        query.assert_not_called()

    def test_logs_and_continues_when_delete_fails(self) -> None:
        now = datetime(2024, 6, 1, tzinfo=UTC)
        stale_deleted_at = (now - timedelta(days=contacts_store.CONTACT_RETENTION_DAYS + 1)).isoformat()
        stored = [
            _stored_full("abc-123", deleted=True, deleted_at=stale_deleted_at),
            _stored_full("def-456", deleted=True, deleted_at=stale_deleted_at),
        ]
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored),
            patch.object(contacts_store.cosmos_store, "delete_document", side_effect=[False, True]),
        ):
            purged = contacts_store.purge_expired_contacts(now=now)

        assert purged == 1


# ---------------------------------------------------------------------------
# list_contacts / contacts_for_flow / contacts_by_flow
# ---------------------------------------------------------------------------


def _stored(contact_id: str, **overrides: object) -> dict:
    data: dict[str, object] = {
        "contact_id": contact_id,
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.nhs.uk",
        "phone_number": "",
        "organisation_type": "Team",
        "organisation_name": "Hub Team",
        "notes": "",
        "flow_ids": ["phw-to-mpi"],
        "deleted": False,
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    data.update(overrides)
    return data


class TestListContacts:
    def test_sorts_by_last_then_first_name(self) -> None:
        stored = [
            _stored("1", first_name="Bob", last_name="Zeta"),
            _stored("2", first_name="Alice", last_name="Alpha"),
        ]
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored):
            contacts, total = contacts_store.list_contacts()
        assert total == 2
        assert [c["last_name"] for c in contacts] == ["Alpha", "Zeta"]

    def test_excludes_deleted_when_include_deleted_is_false(self) -> None:
        stored = [_stored("1", deleted=True), _stored("2", deleted=False)]
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored):
            contacts, total = contacts_store.list_contacts(include_deleted=False)
        assert total == 1
        assert contacts[0]["id"] == "2"

    def test_includes_deleted_by_default(self) -> None:
        stored = [_stored("1", deleted=True), _stored("2", deleted=False)]
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored):
            contacts, total = contacts_store.list_contacts()
        assert total == 2

    def test_filters_by_flow_id(self) -> None:
        stored = [
            _stored("1", flow_ids=["phw-to-mpi"]),
            _stored("2", flow_ids=["paris-to-mpi"]),
        ]
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored):
            contacts, total = contacts_store.list_contacts(flow_id="paris-to-mpi")
        assert total == 1
        assert contacts[0]["id"] == "2"

    def test_filters_by_search_across_fields(self) -> None:
        stored = [
            _stored("1", organisation_name="Hub Team"),
            _stored("2", organisation_name="Acme Supplies"),
        ]
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored):
            contacts, total = contacts_store.list_contacts(search="acme")
        assert total == 1
        assert contacts[0]["id"] == "2"

    def test_paginates_results(self) -> None:
        stored = [_stored(str(i), last_name=f"Person{i:02d}") for i in range(5)]
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored):
            page1, total = contacts_store.list_contacts(page=1, per_page=2)
            page2, _ = contacts_store.list_contacts(page=2, per_page=2)
        assert total == 5
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0]["id"] != page2[0]["id"]


class TestContactsForFlowAndByFlow:
    def test_contacts_for_flow_excludes_deleted(self) -> None:
        stored = [
            _stored("1", flow_ids=["phw-to-mpi"], deleted=False),
            _stored("2", flow_ids=["phw-to-mpi"], deleted=True),
        ]
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored):
            contacts = contacts_store.contacts_for_flow("phw-to-mpi")
        assert len(contacts) == 1
        assert contacts[0]["id"] == "1"

    def test_contacts_by_flow_groups_by_every_linked_flow(self) -> None:
        stored = [_stored("1", flow_ids=["phw-to-mpi", "paris-to-mpi"])]
        with patch.object(contacts_store.cosmos_store, "query_documents", return_value=stored):
            grouped = contacts_store.contacts_by_flow()
        assert set(grouped.keys()) == {"phw-to-mpi", "paris-to-mpi"}
        assert grouped["phw-to-mpi"][0]["id"] == "1"


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------


class TestParseCsv:
    def test_parses_valid_rows(self) -> None:
        csv_text = (
            "first_name,last_name,email,phone_number,organisation_type,organisation_name,flow_ids,notes\n"
            "Jane,Doe,jane@example.nhs.uk,,Team,Hub Team,phw-to-mpi;paris-to-mpi,Primary contact\n"
        )
        rows, errors = contacts_store.parse_csv(csv_text)
        assert errors == []
        assert len(rows) == 1
        assert rows[0]["flow_ids"] == ["phw-to-mpi", "paris-to-mpi"]

    def test_reports_missing_required_columns(self) -> None:
        rows, errors = contacts_store.parse_csv("first_name,last_name\nJane,Doe\n")
        assert rows == []
        assert errors and "missing required column" in errors[0]

    def test_skips_invalid_rows_but_keeps_valid_ones(self) -> None:
        csv_text = (
            "first_name,last_name,email,phone_number,organisation_type,organisation_name,flow_ids,notes\n"
            "Jane,Doe,jane@example.nhs.uk,,Team,Hub Team,,\n"
            ",Missing,bad@example.nhs.uk,,Team,Hub Team,,\n"
        )
        rows, errors = contacts_store.parse_csv(csv_text)
        assert len(rows) == 1
        assert len(errors) == 1
        assert "Row 3" in errors[0]

    def test_empty_file_reports_error(self) -> None:
        rows, errors = contacts_store.parse_csv("")
        assert rows == []
        assert errors == ["CSV file is empty."]


class TestImportContacts:
    def test_creates_new_contacts(self) -> None:
        csv_text = (
            "first_name,last_name,email,phone_number,organisation_type,organisation_name,flow_ids,notes\n"
            "Jane,Doe,jane@example.nhs.uk,,Team,Hub Team,,\n"
        )
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=[]),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True),
        ):
            result = contacts_store.import_contacts(csv_text)
        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["errors"] == []
        assert result["persistence_failed"] is False

    def test_updates_existing_contact_matched_by_email(self) -> None:
        existing = [_stored("abc-123", email="jane.doe@example.nhs.uk")]
        csv_text = (
            "first_name,last_name,email,phone_number,organisation_type,organisation_name,flow_ids,notes\n"
            "Jane,Doe,jane.doe@example.nhs.uk,,Team,Hub Team,,Updated notes\n"
        )
        with (
            patch.object(contacts_store.cosmos_store, "query_documents", return_value=existing),
            patch.object(contacts_store.cosmos_store, "upsert_document", return_value=True) as upsert,
        ):
            result = contacts_store.import_contacts(csv_text)
        assert result["created"] == 0
        assert result["updated"] == 1
        upsert.assert_called_once()
        assert upsert.call_args[0][1] == "abc-123"

    def test_reports_persistence_unavailable(self) -> None:
        csv_text = (
            "first_name,last_name,email,phone_number,organisation_type,organisation_name,flow_ids,notes\n"
            "Jane,Doe,jane@example.nhs.uk,,Team,Hub Team,,\n"
        )
        with patch.object(contacts_store.cosmos_store, "is_configured", return_value=False):
            result = contacts_store.import_contacts(csv_text)
        assert result["persistence_failed"] is True
        assert result["created"] == 0
