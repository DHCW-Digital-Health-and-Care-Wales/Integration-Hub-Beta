from datetime import date, datetime

from flask import Flask, abort, render_template, request

from replay_browser.config import AppConfig, load_config
from replay_browser.db_client import MessageRepository
from replay_browser.hl7_formatter import first_field_value, parse_hl7

ALLOWED_SORT_BY = {"id", "received_at"}
ALLOWED_SORT_DIR = {"asc", "desc"}
ALLOWED_REPLAY_SORT_BY = {"replay_id", "batch_id", "message_id", "status", "created_at"}

def _safe_page(value: str | None) -> int:
    try:
        page = int(value or "1")
    except ValueError:
        return 1
    return 1 if page < 1 else page


def _format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _safe_sort_by(value: str | None) -> str:
    candidate = (value or "id").strip().lower()
    return candidate if candidate in ALLOWED_SORT_BY else "id"


def _safe_sort_dir(value: str | None) -> str:
    candidate = (value or "desc").strip().lower()
    return candidate if candidate in ALLOWED_SORT_DIR else "desc"


def _safe_date(value: str | None) -> date | None:
    if value is None:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    try:
        return datetime.strptime(candidate, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_message_ids(values: list[str]) -> list[int]:
    """Parse posted message id strings into a de-duplicated, sorted list of ints.

    Invalid (non-integer) values are ignored so a malformed form field can't break replay.
    """
    ids: set[int] = set()
    for value in values:
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(ids)


def _safe_replay_sort_by(value: str | None) -> str:
    candidate = (value or "created_at").strip().lower()
    return candidate if candidate in ALLOWED_REPLAY_SORT_BY else "created_at"


def create_app(config: AppConfig | None = None, repository: MessageRepository | None = None) -> Flask:
    app = Flask(__name__)

    resolved_config = config or load_config()
    repo = repository or MessageRepository(
        sql_server=resolved_config.sql_server,
        sql_database=resolved_config.sql_database,
        sql_username=resolved_config.sql_username,
        sql_password=resolved_config.sql_password,
        sql_encrypt=resolved_config.sql_encrypt,
        sql_trust_server_certificate=resolved_config.sql_trust_server_certificate,
    )

    @app.get("/")
    @app.get("/messages")
    def list_messages() -> str:
        page = _safe_page(request.args.get("page"))
        search_query = (request.args.get("q") or "").strip()
        destination = (request.args.get("destination") or "").strip()
        start_date = _safe_date(request.args.get("start_date"))
        end_date = _safe_date(request.args.get("end_date"))
        sort_by = _safe_sort_by(request.args.get("sort_by"))
        sort_dir = _safe_sort_dir(request.args.get("sort_dir"))

        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        results = repo.list_messages(
            page=page,
            page_size=resolved_config.page_size,
            query=search_query,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        start_index = 0 if results.total_rows == 0 else (page - 1) * resolved_config.page_size + 1
        end_index = min(page * resolved_config.page_size, results.total_rows)

        return render_template(
            "messages.html",
            rows=results.rows,
            total_rows=results.total_rows,
            page=page,
            page_size=resolved_config.page_size,
            has_previous=page > 1,
            has_next=end_index < results.total_rows,
            search_query=search_query,
            destination=destination,
            start_date=start_date.isoformat() if start_date else "",
            end_date=end_date.isoformat() if end_date else "",
            sort_by=sort_by,
            sort_dir=sort_dir,
            start_index=start_index,
            end_index=end_index,
            format_timestamp=_format_timestamp,
        )

    @app.get("/messages/<int:message_id>")
    def message_detail(message_id: int) -> str:
        message = repo.get_message(message_id)
        if message is None:
            abort(404)

        segments = parse_hl7(message.raw_payload)
        message_type = first_field_value(segments, "MSH", 9)
        message_control_id = first_field_value(segments, "MSH", 10)
        trigger_event = first_field_value(segments, "EVN", 1)

        return render_template(
            "message_detail.html",
            message=message,
            segments=segments,
            message_type=message_type,
            message_control_id=message_control_id,
            trigger_event=trigger_event,
            format_timestamp=_format_timestamp,
        )

    @app.post("/replay/review")
    def replay_review() -> str:
        """Resolve the selected (or all-filtered) messages and show a review/edit screen."""
        mode = (request.form.get("mode") or "selected").strip().lower()
        search_query = (request.form.get("q") or "").strip()
        destination = (request.form.get("destination") or "").strip()
        start_date = _safe_date(request.form.get("start_date"))
        end_date = _safe_date(request.form.get("end_date"))

        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        if mode == "all_filtered":
            message_ids = repo.list_filtered_message_ids(
                query=search_query,
                destination=destination,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            message_ids = _parse_message_ids(request.form.getlist("message_ids"))

        messages = repo.get_messages_by_ids(message_ids) if message_ids else []

        return render_template(
            "replay_review.html",
            messages=messages,
            mode=mode,
            format_timestamp=_format_timestamp,
        )

    @app.post("/replay/create")
    def replay_create() -> str:
        """Enqueue the confirmed messages, either as a new batch or into an existing one."""
        message_ids = _parse_message_ids(request.form.getlist("message_ids"))
        if not message_ids:
            return render_template("replay_result.html", result=None, message_count=0, added=False)

        existing_batch_id = (request.form.get("existing_batch_id") or "").strip()
        action = (request.form.get("action") or "create").strip().lower()

        if action == "add" and existing_batch_id:
            result = repo.add_messages_to_batch(existing_batch_id, message_ids)
            return render_template(
                "replay_result.html",
                result=result,
                message_count=result.inserted_count,
                added=True,
            )

        result = repo.create_replay_batch(message_ids)
        return render_template(
            "replay_result.html",
            result=result,
            message_count=result.inserted_count,
            added=False,
        )

    @app.get("/replay/queue")
    def replay_queue() -> str:
        """Show the replay queue, filterable by batch reference and created-date, sortable by column."""
        batch_filter = (request.args.get("batch") or "").strip()
        sort_by = _safe_replay_sort_by(request.args.get("sort_by"))
        sort_dir = _safe_sort_dir(request.args.get("sort_dir"))
        start_date = _safe_date(request.args.get("start_date"))
        end_date = _safe_date(request.args.get("end_date"))

        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        entries = repo.list_replay_queue(
            batch_filter=batch_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
            start_date=start_date,
            end_date=end_date,
        )
        batches = repo.list_replay_batches()

        return render_template(
            "replay_queue.html",
            entries=entries,
            batches=batches,
            batch_filter=batch_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
            start_date=start_date.isoformat() if start_date else "",
            end_date=end_date.isoformat() if end_date else "",
            format_timestamp=_format_timestamp,
        )

    @app.post("/replay/queue/remove")
    def replay_queue_remove() -> str:
        """Remove the selected entries from their replay batch, then re-render the queue."""
        replay_ids = _parse_message_ids(request.form.getlist("replay_ids"))
        batch_filter = (request.form.get("batch") or "").strip()
        sort_by = _safe_replay_sort_by(request.form.get("sort_by"))
        sort_dir = _safe_sort_dir(request.form.get("sort_dir"))
        start_date = _safe_date(request.form.get("start_date"))
        end_date = _safe_date(request.form.get("end_date"))

        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        removed_count = repo.remove_replay_entries(replay_ids) if replay_ids else 0

        entries = repo.list_replay_queue(
            batch_filter=batch_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
            start_date=start_date,
            end_date=end_date,
        )
        batches = repo.list_replay_batches()

        return render_template(
            "replay_queue.html",
            entries=entries,
            batches=batches,
            batch_filter=batch_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
            start_date=start_date.isoformat() if start_date else "",
            end_date=end_date.isoformat() if end_date else "",
            removed_count=removed_count,
            format_timestamp=_format_timestamp,
        )

    return app
