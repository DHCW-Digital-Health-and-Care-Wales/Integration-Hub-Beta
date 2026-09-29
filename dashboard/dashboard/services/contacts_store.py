"""Persistence and validation for dashboard Contacts.

Contacts are people (in a Team, Health Board, or Supplier organisation) linked to
one or more integration flows, so support staff can see who to call/email about a
given flow straight from the dashboard. See
``notes/dashboard-contacts-page-design-report.md`` (Integration-Hub-Main workspace)
for the full design.

Storage follows the same generic Cosmos document-store pattern already used for
alarm config/state and flow source servers (see ``cosmos_store.py`` /
``flow_sources.py``): one fixed partition key, one document per contact, and a
best-effort/graceful-degradation posture — every read returns ``[]``/``None``
rather than raising when Cosmos is unconfigured or unreachable.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from dashboard import config
from dashboard.services import cosmos_store
from dashboard.services.flows import get_flows

log = logging.getLogger(__name__)

_PK = "contacts"
_DOC_TYPE = "contact"

_MAX_NAME_LENGTH = 100
_MAX_ORG_NAME_LENGTH = 200
_MAX_NOTES_LENGTH = 2000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[0-9+()\-\s]{5,30}$")

# Confirmed dropdown values for the "organisation type" field.
ORGANISATION_TYPES: tuple[str, ...] = ("Team", "Health Board", "Supplier")

DEFAULT_PAGE_SIZE = 25

# How many days a soft-deleted contact is kept before being permanently purged —
# re-exported here so routes/tests can reference it via ``contacts_store`` without
# reaching into ``dashboard.config`` directly.
CONTACT_RETENTION_DAYS = config.CONTACT_RETENTION_DAYS

_CSV_REQUIRED_FIELDS = ("first_name", "last_name", "organisation_type", "organisation_name")


class InvalidContactError(ValueError):
    """Raised when a supplied contact's fields fail validation."""

    def __init__(self, message: str):
        super().__init__(message)
        self.safe_message = message


class ContactPersistenceError(RuntimeError):
    """Raised when a contact change could not be saved durably."""

    def __init__(self, message: str):
        super().__init__(message)
        self.safe_message = message


_PERSISTENCE_DISABLED_MESSAGE = "Contact persistence is not configured."
_PERSISTENCE_UNAVAILABLE_MESSAGE = "Contact persistence is currently unavailable — please try again shortly."


def _ensure_persistence_configured() -> None:
    if not cosmos_store.is_configured():
        raise ContactPersistenceError(_PERSISTENCE_DISABLED_MESSAGE)


# --- Field validation --------------------------------------------------------


def _validate_name(value: Any, field_label: str) -> str:
    if not isinstance(value, str):
        raise InvalidContactError(f"{field_label} must be a string")
    value = value.strip()
    if not value:
        raise InvalidContactError(f"{field_label} must not be empty")
    if len(value) > _MAX_NAME_LENGTH:
        raise InvalidContactError(f"{field_label} is too long (max {_MAX_NAME_LENGTH} characters)")
    return value


def _validate_email(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidContactError("Email must be a string")
    value = value.strip().lower()
    if value and not _EMAIL_RE.match(value):
        raise InvalidContactError("Email is not a valid email address")
    return value


def _validate_phone(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidContactError("Phone number must be a string")
    value = value.strip()
    if value and not _PHONE_RE.match(value):
        raise InvalidContactError("Phone number may only contain digits, spaces, +, (), and -")
    return value


def _validate_organisation_type(value: Any) -> str:
    if not isinstance(value, str) or value.strip() not in ORGANISATION_TYPES:
        raise InvalidContactError(f"Organisation type must be one of: {', '.join(ORGANISATION_TYPES)}")
    return value.strip()


def _validate_organisation_name(value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidContactError("Organisation name must be a string")
    value = value.strip()
    if not value:
        raise InvalidContactError("Organisation name must not be empty")
    if len(value) > _MAX_ORG_NAME_LENGTH:
        raise InvalidContactError(f"Organisation name is too long (max {_MAX_ORG_NAME_LENGTH} characters)")
    return value


def _validate_notes(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidContactError("Notes must be a string")
    value = value.strip()
    if len(value) > _MAX_NOTES_LENGTH:
        raise InvalidContactError(f"Notes are too long (max {_MAX_NOTES_LENGTH} characters)")
    return value


def _validate_flow_ids(value: Any) -> list[str]:
    """Validate linked flow ids against currently known flows.

    Falls back to accepting the supplied ids unchanged when no flow definitions are
    available (e.g. local dev without Azure credentials configured) — matching the
    dashboard's established graceful-degradation behaviour elsewhere, rather than
    blocking every contact save whenever flow discovery is down.
    """
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise InvalidContactError("Linked flows must be a list of flow ids")

    flow_ids = [v.strip() for v in value if v.strip()]

    try:
        known_ids = set(get_flows().keys())
    except Exception as exc:  # noqa: BLE001 - flow discovery must never block a contact save
        log.warning("Could not validate linked flow ids against live flow discovery: %s", exc)
        known_ids = set()

    if known_ids:
        unknown = [flow_id for flow_id in flow_ids if flow_id not in known_ids]
        if unknown:
            raise InvalidContactError(f"Unknown flow id(s): {', '.join(unknown)}")

    seen: set[str] = set()
    deduped: list[str] = []
    for flow_id in flow_ids:
        if flow_id not in seen:
            seen.add(flow_id)
            deduped.append(flow_id)
    return deduped


def _validate_contact(data: dict[str, Any]) -> dict[str, Any]:
    """Validate every contact field, raising InvalidContactError on the first problem."""
    first_name = _validate_name(data.get("first_name", ""), "First name")
    last_name = _validate_name(data.get("last_name", ""), "Last name")
    email = _validate_email(data.get("email"))
    phone_number = _validate_phone(data.get("phone_number"))
    if not email and not phone_number:
        raise InvalidContactError("Either an email address or a phone number is required")
    organisation_type = _validate_organisation_type(data.get("organisation_type", ""))
    organisation_name = _validate_organisation_name(data.get("organisation_name", ""))
    notes = _validate_notes(data.get("notes"))
    flow_ids = _validate_flow_ids(data.get("flow_ids"))

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone_number,
        "organisation_type": organisation_type,
        "organisation_name": organisation_name,
        "notes": notes,
        "flow_ids": flow_ids,
    }


# --- Storage -------------------------------------------------------------


def _with_id(document: dict[str, Any]) -> dict[str, Any]:
    """Map the persisted "contact_id" field back onto the public "id" key.

    ``cosmos_store`` treats "id" as Cosmos routing metadata and strips it from every
    document it returns, so a contact's id is instead stored under "contact_id" (not
    a reserved key), which comes back unchanged on read.
    """
    contact = {k: v for k, v in document.items() if k != "contact_id"}
    contact["id"] = document.get("contact_id")
    return contact


def _list_all() -> list[dict[str, Any]]:
    """Return every stored contact document, including soft-deleted ones."""
    return [_with_id(document) for document in cosmos_store.query_documents(_PK)]


def _find(contact_id: str) -> dict[str, Any] | None:
    for contact in _list_all():
        if contact.get("id") == contact_id:
            return contact
    return None


def _persist(contact_id: str, contact: dict[str, Any]) -> None:
    payload = {k: v for k, v in contact.items() if k not in ("id", "contact_id")}
    payload["contact_id"] = contact_id
    if not cosmos_store.upsert_document(_PK, contact_id, payload, doc_type=_DOC_TYPE):
        raise ContactPersistenceError(_PERSISTENCE_UNAVAILABLE_MESSAGE)


# --- Public API ------------------------------------------------------------


def get_contact(contact_id: str) -> dict[str, Any] | None:
    """Return a single contact by id, or None if it doesn't exist."""
    return _find(contact_id)


def _matches_search(contact: dict[str, Any], search: str) -> bool:
    haystack = " ".join(
        str(contact.get(field, ""))
        for field in ("first_name", "last_name", "email", "phone_number", "organisation_name", "organisation_type")
    ).lower()
    return search.lower() in haystack


def list_contacts(
    search: str | None = None,
    flow_id: str | None = None,
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
    include_deleted: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    """Return a page of contacts matching the given filters, plus the total match count.

    Soft-deleted contacts are included by default and simply carry ``deleted: true``
    for the UI to badge — per the confirmed design, deleted contacts stay visible to
    everyone for now (no admin-only recovery view yet).

    Filtering, sorting, and pagination all happen in-memory over the full partition,
    which is fine at the expected contact volumes (tens to low hundreds).
    """
    contacts = _list_all()
    if not include_deleted:
        contacts = [c for c in contacts if not c.get("deleted")]
    if flow_id:
        contacts = [c for c in contacts if flow_id in (c.get("flow_ids") or [])]
    if search:
        contacts = [c for c in contacts if _matches_search(c, search)]

    contacts.sort(key=lambda c: (str(c.get("last_name", "")).lower(), str(c.get("first_name", "")).lower()))

    total = len(contacts)
    per_page = max(1, per_page)
    page = max(1, page)
    start = (page - 1) * per_page
    return contacts[start : start + per_page], total


def contacts_for_flow(flow_id: str) -> list[dict[str, Any]]:
    """Return every non-deleted contact linked to the given flow, sorted by name."""
    contacts, _ = list_contacts(flow_id=flow_id, per_page=1_000_000, include_deleted=False)
    return contacts


def contacts_by_flow() -> dict[str, list[dict[str, Any]]]:
    """Return every non-deleted contact grouped by linked flow id, in one partition query.

    Used by the Flows page so it can show linked contacts per flow without running
    one query per flow card.
    """
    contacts, _ = list_contacts(per_page=1_000_000, include_deleted=False)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for contact in contacts:
        for flow_id in contact.get("flow_ids") or []:
            grouped.setdefault(flow_id, []).append(contact)
    return grouped


def add_contact(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist a new contact, returning the stored document."""
    contact = _validate_contact(data)
    _ensure_persistence_configured()

    now = datetime.now(UTC).isoformat()
    contact_id = str(uuid.uuid4())
    contact.update({"deleted": False, "created_at": now, "updated_at": now})
    _persist(contact_id, contact)
    contact["id"] = contact_id
    return contact


def update_contact(contact_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Validate and overwrite an existing contact, returning the stored document."""
    existing = _find(contact_id)
    if existing is None:
        raise InvalidContactError("Contact not found.")

    contact = _validate_contact(data)
    _ensure_persistence_configured()
    contact.update(
        {
            "deleted": existing.get("deleted", False),
            "created_at": existing.get("created_at") or datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    _persist(contact_id, contact)
    contact["id"] = contact_id
    return contact


def delete_contact(contact_id: str) -> None:
    """Soft-delete a contact by setting ``deleted: true`` — a no-op if already gone.

    Confirmed team decision: this is a soft delete, not a hard delete. Deleted
    contacts remain visible to everyone (no admin gate yet — see the design report)
    but are excluded from ``list_contacts(include_deleted=False)``/
    ``contacts_for_flow()``/``contacts_by_flow()`` by default. The ``deleted_at``
    timestamp recorded here is what :func:`purge_expired_contacts` later uses to
    decide when the retention window has elapsed.
    """
    existing = _find(contact_id)
    if existing is None:
        return
    _ensure_persistence_configured()
    now = datetime.now(UTC).isoformat()
    existing["deleted"] = True
    existing["deleted_at"] = now
    existing["updated_at"] = now
    _persist(contact_id, existing)


def restore_contact(contact_id: str) -> dict[str, Any] | None:
    """Reverse a soft delete by setting ``deleted: false`` — a no-op if already gone.

    Clears ``deleted_at`` so a subsequently re-deleted contact starts a fresh
    retention window. Returns the restored contact document (with ``id`` set), or
    ``None`` if no contact exists with that id.
    """
    existing = _find(contact_id)
    if existing is None:
        return None
    _ensure_persistence_configured()
    existing["deleted"] = False
    existing["deleted_at"] = None
    existing["updated_at"] = datetime.now(UTC).isoformat()
    _persist(contact_id, existing)
    existing["id"] = contact_id
    return existing


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp string, defaulting a missing timezone to UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def purge_expired_contacts(now: datetime | None = None) -> int:
    """Permanently delete soft-deleted contacts past the retention window.

    Confirmed retention policy: a contact that has been soft-deleted (and not
    restored) for more than ``CONTACT_RETENTION_DAYS`` (default 90, see
    ``CONTACT_RETENTION_DAYS`` env var) days is permanently removed from Cosmos —
    this is a genuine hard delete, unlike :func:`delete_contact`.

    Falls back to ``updated_at`` for contacts soft-deleted before ``deleted_at``
    existed. Contacts with no parseable timestamp at all are left alone rather
    than purged, since we can't safely tell how long they've been deleted.

    Returns the number of contacts permanently deleted. A no-op (returns 0) when
    persistence isn't configured, matching the rest of this module's graceful
    degradation behaviour.
    """
    if not cosmos_store.is_configured():
        return 0

    cutoff = (now or datetime.now(UTC)) - timedelta(days=CONTACT_RETENTION_DAYS)

    purged = 0
    for contact in _list_all():
        if not contact.get("deleted"):
            continue
        deleted_at = _parse_timestamp(contact.get("deleted_at")) or _parse_timestamp(contact.get("updated_at"))
        if deleted_at is None or deleted_at > cutoff:
            continue

        contact_id = contact.get("id")
        if not contact_id:
            continue
        if cosmos_store.delete_document(_PK, contact_id):
            purged += 1
        else:
            log.warning("Failed to permanently delete expired contact %s", contact_id)

    return purged


# --- CSV import ------------------------------------------------------------


def parse_csv(file_content: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse CSV text into validated contact rows.

    Expects a header row containing at least ``first_name``, ``last_name``,
    ``organisation_type`` and ``organisation_name`` (matched case-insensitively, in
    any column order). Optional columns: ``email``, ``phone_number``, ``flow_ids``
    (``;``-separated flow ids in one cell), ``notes``. Invalid rows are skipped
    (with an error message) rather than aborting the whole import.
    """
    reader = csv.DictReader(io.StringIO(file_content))
    if reader.fieldnames is None:
        return [], ["CSV file is empty."]

    normalized_fields = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = [field for field in _CSV_REQUIRED_FIELDS if field not in normalized_fields]
    if missing:
        return [], [f"CSV header is missing required column(s): {', '.join(missing)}"]

    def _column(row: dict[str, str], name: str) -> str:
        key = normalized_fields.get(name)
        return (row.get(key) or "") if key else ""

    valid_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for row_number, row in enumerate(reader, start=2):  # row 1 is the header
        flow_ids_raw = _column(row, "flow_ids")
        flow_ids = [f.strip() for f in flow_ids_raw.split(";") if f.strip()] if flow_ids_raw else []
        try:
            contact = _validate_contact(
                {
                    "first_name": _column(row, "first_name"),
                    "last_name": _column(row, "last_name"),
                    "email": _column(row, "email"),
                    "phone_number": _column(row, "phone_number"),
                    "organisation_type": _column(row, "organisation_type"),
                    "organisation_name": _column(row, "organisation_name"),
                    "notes": _column(row, "notes"),
                    "flow_ids": flow_ids,
                }
            )
        except InvalidContactError as exc:
            errors.append(f"Row {row_number}: {exc.safe_message}")
            continue
        valid_rows.append(contact)

    return valid_rows, errors


def _dedupe_key(contact: dict[str, Any]) -> str | None:
    """Return the natural key used to match an imported row against an existing contact.

    Proposed rule (flagged in the design report as not yet confirmed by the team):
    match by email (case-insensitive) when present, otherwise by phone number. Kept
    as a single small function so the matching rule is easy to change later without
    touching the rest of the import pipeline.
    """
    if contact.get("email"):
        return f"email:{contact['email'].lower()}"
    if contact.get("phone_number"):
        return f"phone:{contact['phone_number']}"
    return None


def import_contacts(file_content: str) -> dict[str, Any]:
    """Parse and persist every valid row from an uploaded CSV file.

    Returns a summary: ``{"created": <count>, "updated": <count>, "errors": [...],
    "persistence_failed": <bool>}``.
    """
    valid_rows, errors = parse_csv(file_content)
    try:
        _ensure_persistence_configured()
    except ContactPersistenceError as exc:
        errors.append(exc.safe_message)
        return {"created": 0, "updated": 0, "errors": errors, "persistence_failed": True}

    existing_by_key: dict[str, dict[str, Any]] = {}
    for contact in _list_all():
        key = _dedupe_key(contact)
        if key:
            existing_by_key[key] = contact

    created = 0
    updated = 0
    persistence_failed = False
    for row in valid_rows:
        label = f"{row['first_name']} {row['last_name']}"
        key = _dedupe_key(row)
        match = existing_by_key.get(key) if key else None
        try:
            if match:
                update_contact(match["id"], row)
                updated += 1
            else:
                add_contact(row)
                created += 1
        except InvalidContactError as exc:
            errors.append(f"{label}: {exc.safe_message}")
        except ContactPersistenceError as exc:
            errors.append(f"{label}: {exc.safe_message}")
            persistence_failed = True
            break

    return {"created": created, "updated": updated, "errors": errors, "persistence_failed": persistence_failed}
