"""Contacts page and JSON API routes.

Follows the same plain-view-function + ``register(app)`` pattern as the other
route modules (see ``dashboard.routes`` package docstring for why these aren't
Flask ``Blueprint`` objects). The Contacts page reuses the JSON-API-driven,
JavaScript-rendered table pattern already established for the Flow Source
Servers configuration screen (``dashboard.routes.api.api_network_test_sources``
+ ``network_test_config.html``) — search/pagination/add/edit/delete/import all
happen via ``fetch()`` calls against the ``/api/contacts...`` endpoints defined
here, with no full-page reloads.
"""

from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, render_template, request

from dashboard.services import cache, contacts_store
from dashboard.services.flows import get_active_flows

log = logging.getLogger(__name__)

# Uploaded CSV files are read fully into memory (a handful of rows of plain text
# at most), so an explicit size cap guards against an oversized upload exhausting
# memory — mirrors ``api._MAX_IMPORT_CSV_BYTES`` for flow source server imports.
_MAX_IMPORT_CSV_BYTES = 1_000_000

# Cadence for the soft-delete retention purge (see contacts_store.purge_expired_contacts).
# Reuses the generic TTL cache as a cheap once-a-day gate rather than adding a
# dedicated background scheduler for what is a low-urgency housekeeping task.
_PURGE_CHECK_TTL_SECONDS = 24 * 60 * 60


def _check_expired_contacts() -> None:
    """Run the soft-delete retention purge at most once per day, without blocking the page.

    Piggy-backs on a Contacts page view rather than requiring a separate scheduled
    job/container — acceptable because the 90-day retention window has no real-time
    precision requirement. Errors are logged and swallowed so a purge failure never
    breaks the page.
    """
    try:
        cache.cached_nowait("contacts_purge", contacts_store.purge_expired_contacts, ttl=_PURGE_CHECK_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - housekeeping must never break the Contacts page
        log.warning("Contact retention purge check failed: %s", exc)


def contacts_page() -> str:
    """Render the Contacts page shell — the contact list itself is loaded via JS."""
    _check_expired_contacts()
    flows = get_active_flows() or {}
    flow_options = [{"id": flow_id, "label": flow.get("label", flow_id)} for flow_id, flow in flows.items()]
    flow_options.sort(key=lambda option: option["label"])
    # All data the page's <script> needs is bundled into one JSON blob (rendered into
    # a <script type="application/json"> tag and JSON.parse()'d client-side) rather
    # than interpolated as bare Jinja expressions/loops inside the main <script>
    # block — raw `{{ }}`/`{% %}` tokens there aren't valid JavaScript syntax on
    # their own, which breaks static JS tooling (linters/language servers) even
    # though Jinja renders it into valid JS in the end.
    page_data = {
        "default_page_size": contacts_store.DEFAULT_PAGE_SIZE,
        "contact_retention_days": contacts_store.CONTACT_RETENTION_DAYS,
        "flow_labels": {option["id"]: option["label"] for option in flow_options},
    }
    return render_template(
        "contacts.html",
        flow_options=flow_options,
        organisation_types=contacts_store.ORGANISATION_TYPES,
        page_data=page_data,
    )


def api_contacts() -> tuple[Response, int] | Response:
    """GET returns a page of contacts; POST creates a new contact from a JSON body."""
    if request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "JSON body must be an object"}), 400
        try:
            contact = contacts_store.add_contact(payload)
        except contacts_store.InvalidContactError as exc:
            return jsonify({"error": exc.safe_message}), 400
        except contacts_store.ContactPersistenceError as exc:
            return jsonify({"error": exc.safe_message}), 503
        return jsonify(contact), 201

    search = (request.args.get("q") or "").strip() or None
    flow_id = (request.args.get("flow") or "").strip() or None
    include_deleted = (request.args.get("include_deleted") or "true").lower() != "false"
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        per_page = max(1, int(request.args.get("per_page", contacts_store.DEFAULT_PAGE_SIZE)))
    except ValueError:
        per_page = contacts_store.DEFAULT_PAGE_SIZE

    contacts, total = contacts_store.list_contacts(
        search=search,
        flow_id=flow_id,
        page=page,
        per_page=per_page,
        include_deleted=include_deleted,
    )
    return jsonify({"contacts": contacts, "total": total, "page": page, "per_page": per_page})


def api_contact(contact_id: str) -> tuple[Response, int] | Response:
    """GET returns one contact; PUT updates it; DELETE soft-deletes it."""
    if request.method == "DELETE":
        contacts_store.delete_contact(contact_id)
        return jsonify({"deleted": True, "id": contact_id})

    if request.method == "PUT":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "JSON body must be an object"}), 400
        try:
            contact = contacts_store.update_contact(contact_id, payload)
        except contacts_store.InvalidContactError as exc:
            return jsonify({"error": exc.safe_message}), 400
        except contacts_store.ContactPersistenceError as exc:
            return jsonify({"error": exc.safe_message}), 503
        return jsonify(contact)

    found_contact = contacts_store.get_contact(contact_id)
    if found_contact is None:
        return jsonify({"error": "Contact not found."}), 404
    return jsonify(found_contact)


def api_contact_restore(contact_id: str) -> tuple[Response, int] | Response:
    """POST restores a soft-deleted contact by clearing its ``deleted`` flag."""
    try:
        contact = contacts_store.restore_contact(contact_id)
    except contacts_store.ContactPersistenceError as exc:
        return jsonify({"error": exc.safe_message}), 503
    if contact is None:
        return jsonify({"error": "Contact not found."}), 404
    return jsonify(contact)


def api_contacts_import() -> tuple[Response, int] | Response:
    """POST a CSV file (multipart field "file") to bulk-import/update contacts."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "No CSV file uploaded."}), 400

    raw = upload.read(_MAX_IMPORT_CSV_BYTES + 1)
    if len(raw) > _MAX_IMPORT_CSV_BYTES:
        return jsonify({"error": "CSV file is too large."}), 400

    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"error": "CSV file must be UTF-8 encoded."}), 400

    result = contacts_store.import_contacts(content)
    if result["persistence_failed"]:
        return jsonify(result), 503
    return jsonify(result)


def register(app: Flask) -> None:
    """Register the Contacts page and JSON API routes onto ``app``."""
    app.add_url_rule("/contacts", endpoint="contacts_page", view_func=contacts_page)
    app.add_url_rule("/api/contacts", endpoint="api_contacts", view_func=api_contacts, methods=["GET", "POST"])
    app.add_url_rule(
        "/api/contacts/import", endpoint="api_contacts_import", view_func=api_contacts_import, methods=["POST"]
    )
    app.add_url_rule(
        "/api/contacts/<contact_id>",
        endpoint="api_contact",
        view_func=api_contact,
        methods=["GET", "PUT", "DELETE"],
    )
    app.add_url_rule(
        "/api/contacts/<contact_id>/restore",
        endpoint="api_contact_restore",
        view_func=api_contact_restore,
        methods=["POST"],
    )
