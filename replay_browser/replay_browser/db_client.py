import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence

ODBC_DRIVER = "{ODBC Driver 18 for SQL Server}"
SORT_COLUMN_MAP = {
    "id": "Id",
    "received_at": "ReceivedAt",
}
SORT_DIRECTION_MAP = {
    "asc": "ASC",
    "desc": "DESC",
}

# Sortable columns for the replay queue screen. Keys are the public sort tokens accepted from
# the UI; values are the trusted column names used to build the ORDER BY clause.
REPLAY_SORT_COLUMN_MAP = {
    "replay_id": "ReplayId",
    "batch_id": "ReplayBatchId",
    "message_id": "MessageId",
    "status": "Status",
    "created_at": "CreatedAt",
}

# Shared WHERE predicate for the list/search/replay-selection queries. Every clause is
# parameterised so callers can pass user input safely. The empty-string / NULL guards make
# each filter optional without rebuilding the SQL string per request.
_FILTER_CLAUSE = """
    (? = '' OR CorrelationId LIKE ? OR SourceSystem LIKE ? OR RawPayload LIKE ?)
      AND (? = '' OR TargetSystem LIKE ?)
      AND (? IS NULL OR ReceivedAt >= ?)
      AND (? IS NULL OR ReceivedAt < ?)
"""


def _build_filter_params(
    query: str,
    destination: str,
    start_date: date | None,
    end_date: date | None,
) -> tuple[Any, ...]:
    """Build the parameter tuple matching the placeholders in ``_FILTER_CLAUSE``."""
    trimmed_query = query.strip()
    sql_like = f"%{trimmed_query}%"
    trimmed_destination = destination.strip()
    destination_like = f"%{trimmed_destination}%"
    start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
    # End date is inclusive: convert it to an exclusive upper bound at the start of the next day.
    end_datetime_exclusive = (
        datetime.combine(end_date + timedelta(days=1), datetime.min.time()) if end_date else None
    )
    return (
        trimmed_query,
        sql_like,
        sql_like,
        sql_like,
        trimmed_destination,
        destination_like,
        start_datetime,
        start_datetime,
        end_datetime_exclusive,
        end_datetime_exclusive,
    )


@dataclass(frozen=True)
class MessageSummary:
    id: int
    received_at: datetime
    stored_at: datetime
    correlation_id: str
    source_system: str
    processing_component: str
    target_system: str | None
    session_id: str


@dataclass(frozen=True)
class MessageDetail:
    id: int
    received_at: datetime
    stored_at: datetime
    correlation_id: str
    source_system: str
    processing_component: str
    target_system: str | None
    session_id: str
    raw_payload: str
    xml_payload: str | None


@dataclass(frozen=True)
class MessageSearchResult:
    rows: list[MessageSummary]
    total_rows: int


@dataclass(frozen=True)
class ReplayBatchResult:
    """Outcome of enqueuing a replay batch into monitoring.MessageReplayQueue."""

    batch_id: str
    inserted_count: int


@dataclass(frozen=True)
class ReplayQueueEntry:
    """A single row in monitoring.MessageReplayQueue, enriched with message context."""

    replay_id: int
    batch_id: str
    message_id: int
    status: str
    created_at: datetime
    processed_at: datetime | None
    correlation_id: str | None
    source_system: str | None
    target_system: str | None


@dataclass(frozen=True)
class ReplayBatchSummary:
    """Aggregated view of a replay batch, for the batch filter / overview."""

    batch_id: str
    total: int
    pending: int
    created_at: datetime



class MessageRepository:
    def __init__(
        self,
        sql_server: str,
        sql_database: str,
        sql_username: str | None,
        sql_password: str | None,
        sql_encrypt: str,
        sql_trust_server_certificate: str,
    ) -> None:
        self._sql_server = sql_server
        self._sql_database = sql_database
        self._sql_username = sql_username
        self._sql_password = sql_password
        self._sql_encrypt = sql_encrypt
        self._sql_trust_server_certificate = sql_trust_server_certificate

    def _connection_string(self) -> str:
        base = (
            f"DRIVER={ODBC_DRIVER};"
            f"SERVER={self._sql_server};"
            f"DATABASE={self._sql_database};"
            f"Encrypt={self._sql_encrypt};"
            f"TrustServerCertificate={self._sql_trust_server_certificate};"
        )

        if self._sql_username and self._sql_password:
            return f"{base}UID={self._sql_username};PWD={self._sql_password};"

        return f"{base}Authentication=ActiveDirectoryMsi"

    def _connect(self) -> Any:
        # Lazy import keeps unit tests independent of local unixODBC installation.
        import pyodbc  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        return pyodbc.connect(self._connection_string(), autocommit=False)

    def list_messages(
        self,
        page: int,
        page_size: int,
        query: str,
        destination: str,
        start_date: date | None,
        end_date: date | None,
        sort_by: str,
        sort_dir: str,
    ) -> MessageSearchResult:
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1:
            raise ValueError("page_size must be >= 1")

        sort_column = SORT_COLUMN_MAP.get(sort_by)
        if sort_column is None:
            raise ValueError("sort_by must be one of: id, received_at")

        sort_direction = SORT_DIRECTION_MAP.get(sort_dir)
        if sort_direction is None:
            raise ValueError("sort_dir must be one of: asc, desc")

        offset = (page - 1) * page_size
        query_params = _build_filter_params(query, destination, start_date, end_date)

        count_sql = f"""
            SELECT COUNT(*)
            FROM monitoring.Message
            WHERE {_FILTER_CLAUSE}
        """  # nosec B608 — _FILTER_CLAUSE is a trusted constant; all values are parameterised

        rows_sql = f"""
            SELECT Id, ReceivedAt, StoredAt, CorrelationId, SourceSystem, ProcessingComponent, TargetSystem, SessionId
            FROM monitoring.Message
            WHERE {_FILTER_CLAUSE}
            ORDER BY {sort_column} {sort_direction}
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """  # nosec B608 — _FILTER_CLAUSE and sort tokens come from trusted maps; values are parameterised

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(count_sql, query_params)
            total_rows = int(cursor.fetchone()[0])

            cursor.execute(rows_sql, (*query_params, offset, page_size))
            raw_rows = cursor.fetchall()

        rows = [
            MessageSummary(
                id=int(row[0]),
                received_at=row[1],
                stored_at=row[2],
                correlation_id=str(row[3]),
                source_system=str(row[4]),
                processing_component=str(row[5]),
                target_system=str(row[6]) if row[6] is not None else None,
                session_id=str(row[7]),
            )
            for row in raw_rows
        ]

        return MessageSearchResult(rows=rows, total_rows=total_rows)

    def list_filtered_message_ids(
        self,
        query: str,
        destination: str,
        start_date: date | None,
        end_date: date | None,
    ) -> list[int]:
        """Return the Ids of every message matching the given filters (all pages).

        Used by the "replay all matching filters" action so the replay batch can span the
        full result set rather than just the page currently shown in the browser.
        """
        params = _build_filter_params(query, destination, start_date, end_date)
        sql = f"""
            SELECT Id
            FROM monitoring.Message
            WHERE {_FILTER_CLAUSE}
            ORDER BY Id
        """  # nosec B608 — _FILTER_CLAUSE is a trusted constant; all values are parameterised

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [int(row[0]) for row in cursor.fetchall()]

    def get_messages_by_ids(self, message_ids: Sequence[int]) -> list[MessageSummary]:
        """Return summaries for the given message Ids, ordered by Id.

        Only Ids that exist in monitoring.Message are returned, so callers can rely on the
        result reflecting the messages that would actually be enqueued for replay.
        """
        unique_ids = sorted({int(message_id) for message_id in message_ids})
        if not unique_ids:
            return []

        placeholders = ", ".join("?" for _ in unique_ids)
        sql = f"""
            SELECT Id, ReceivedAt, StoredAt, CorrelationId, SourceSystem, ProcessingComponent, TargetSystem, SessionId
            FROM monitoring.Message
            WHERE Id IN ({placeholders})
            ORDER BY Id
        """  # nosec B608 — placeholders are parameterised ? markers, not user input

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, unique_ids)
            raw_rows = cursor.fetchall()

        return [
            MessageSummary(
                id=int(row[0]),
                received_at=row[1],
                stored_at=row[2],
                correlation_id=str(row[3]),
                source_system=str(row[4]),
                processing_component=str(row[5]),
                target_system=str(row[6]) if row[6] is not None else None,
                session_id=str(row[7]),
            )
            for row in raw_rows
        ]

    def create_replay_batch(self, message_ids: Sequence[int]) -> ReplayBatchResult:
        """Enqueue the given messages into monitoring.MessageReplayQueue under a new batch.

        Generates a fresh ReplayBatchId (UUID) and inserts one Pending row per message. The
        INSERT selects from monitoring.Message so only existing Ids are enqueued (preserving
        referential integrity), and the table's unique (ReplayBatchId, MessageId) index makes
        duplicates within the batch impossible.

        The browser only *enqueues* the batch; the separate message_replay_job container is
        what actually publishes the messages to Service Bus when run with this batch id.

        Returns:
            ReplayBatchResult with the generated batch id and the number of rows enqueued.

        Raises:
            ValueError: If no message ids are supplied.
            pyodbc.Error: On any database-level failure.
        """
        unique_ids = sorted({int(message_id) for message_id in message_ids})
        if not unique_ids:
            raise ValueError("At least one message id is required to create a replay batch")

        batch_id = str(uuid.uuid4())
        insert_sql = """
            INSERT INTO monitoring.MessageReplayQueue (ReplayBatchId, MessageId)
            SELECT ?, m.Id
            FROM monitoring.Message m
            WHERE m.Id = ?
        """
        count_sql = "SELECT COUNT(*) FROM monitoring.MessageReplayQueue WHERE ReplayBatchId = ?"

        with self._connect() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(insert_sql, [(batch_id, message_id) for message_id in unique_ids])
                cursor.execute(count_sql, (batch_id,))
                inserted_count = int(cursor.fetchone()[0])
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return ReplayBatchResult(batch_id=batch_id, inserted_count=inserted_count)

    def list_replay_batches(self) -> list[ReplayBatchSummary]:
        """Return one summary row per replay batch, newest first.

        Used to populate the batch filter and give an at-a-glance overview of how many
        messages each batch holds and how many are still Pending.
        """
        sql = """
            SELECT
                CONVERT(NVARCHAR(36), ReplayBatchId) AS BatchId,
                COUNT(*) AS Total,
                SUM(CASE WHEN Status = 'Pending' THEN 1 ELSE 0 END) AS Pending,
                MIN(CreatedAt) AS CreatedAt
            FROM monitoring.MessageReplayQueue
            GROUP BY ReplayBatchId
            ORDER BY MIN(CreatedAt) DESC
        """

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            raw_rows = cursor.fetchall()

        return [
            ReplayBatchSummary(
                batch_id=str(row[0]),
                total=int(row[1]),
                pending=int(row[2]),
                created_at=row[3],
            )
            for row in raw_rows
        ]

    def list_replay_queue(
        self,
        batch_filter: str,
        sort_by: str,
        sort_dir: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ReplayQueueEntry]:
        """Return replay queue entries, optionally filtered by (partial) batch reference and date.

        The batch filter matches against the text form of ReplayBatchId, so callers can pass a
        full batch id or just a fragment. The optional ``start_date`` / ``end_date`` bounds filter
        on the entry's ``CreatedAt`` (end date is inclusive). Sorting is restricted to a trusted
        column map.
        """
        sort_column = REPLAY_SORT_COLUMN_MAP.get(sort_by)
        if sort_column is None:
            raise ValueError("sort_by must be one of: replay_id, batch_id, message_id, status, created_at")

        sort_direction = SORT_DIRECTION_MAP.get(sort_dir)
        if sort_direction is None:
            raise ValueError("sort_dir must be one of: asc, desc")

        trimmed_filter = batch_filter.strip()
        filter_like = f"%{trimmed_filter}%"
        start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
        # End date is inclusive: convert it to an exclusive upper bound at the start of the next day.
        end_datetime_exclusive = (
            datetime.combine(end_date + timedelta(days=1), datetime.min.time()) if end_date else None
        )

        sql = f"""
            SELECT
                q.ReplayId,
                CONVERT(NVARCHAR(36), q.ReplayBatchId) AS BatchId,
                q.MessageId,
                q.Status,
                q.CreatedAt,
                q.ProcessedAt,
                m.CorrelationId,
                m.SourceSystem,
                m.TargetSystem
            FROM monitoring.MessageReplayQueue q
            LEFT JOIN monitoring.Message m ON m.Id = q.MessageId
            WHERE (? = '' OR CONVERT(NVARCHAR(36), q.ReplayBatchId) LIKE ?)
              AND (? IS NULL OR q.CreatedAt >= ?)
              AND (? IS NULL OR q.CreatedAt < ?)
            ORDER BY q.{sort_column} {sort_direction}
        """  # nosec B608 — sort tokens come from trusted maps; all values are parameterised

        params = (
            trimmed_filter,
            filter_like,
            start_datetime,
            start_datetime,
            end_datetime_exclusive,
            end_datetime_exclusive,
        )

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            raw_rows = cursor.fetchall()

        return [
            ReplayQueueEntry(
                replay_id=int(row[0]),
                batch_id=str(row[1]),
                message_id=int(row[2]),
                status=str(row[3]),
                created_at=row[4],
                processed_at=row[5],
                correlation_id=str(row[6]) if row[6] is not None else None,
                source_system=str(row[7]) if row[7] is not None else None,
                target_system=str(row[8]) if row[8] is not None else None,
            )
            for row in raw_rows
        ]

    def add_messages_to_batch(self, batch_id: str, message_ids: Sequence[int]) -> ReplayBatchResult:
        """Add the given messages to an existing replay batch.

        Inserts are idempotent: a message is only enqueued if it exists in monitoring.Message
        and is not already present in the batch, so re-adding the same message is a no-op and
        the unique (ReplayBatchId, MessageId) index is never violated.

        Returns:
            ReplayBatchResult with the batch id and the number of *new* rows added.

        Raises:
            ValueError: If the batch id is missing or no message ids are supplied.
            pyodbc.Error: On any database-level failure.
        """
        normalised_batch_id = batch_id.strip()
        if not normalised_batch_id:
            raise ValueError("A batch id is required to add messages to a batch")

        unique_ids = sorted({int(message_id) for message_id in message_ids})
        if not unique_ids:
            raise ValueError("At least one message id is required to add to a batch")

        insert_sql = """
            INSERT INTO monitoring.MessageReplayQueue (ReplayBatchId, MessageId)
            SELECT ?, m.Id
            FROM monitoring.Message m
            WHERE m.Id = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM monitoring.MessageReplayQueue q
                  WHERE q.ReplayBatchId = ? AND q.MessageId = m.Id
              )
        """

        with self._connect() as conn:
            cursor = conn.cursor()
            try:
                added = 0
                for message_id in unique_ids:
                    cursor.execute(insert_sql, (normalised_batch_id, message_id, normalised_batch_id))
                    added += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return ReplayBatchResult(batch_id=normalised_batch_id, inserted_count=added)

    def remove_replay_entries(self, replay_ids: Sequence[int]) -> int:
        """Remove the given queue entries (by ReplayId) from monitoring.MessageReplayQueue.

        Returns:
            The number of rows actually deleted.

        Raises:
            ValueError: If no replay ids are supplied.
            pyodbc.Error: On any database-level failure.
        """
        unique_ids = sorted({int(replay_id) for replay_id in replay_ids})
        if not unique_ids:
            raise ValueError("At least one replay id is required to remove entries")

        placeholders = ", ".join("?" for _ in unique_ids)
        delete_sql = f"""
            DELETE FROM monitoring.MessageReplayQueue
            WHERE ReplayId IN ({placeholders})
        """  # nosec B608 — placeholders are parameterised ? markers, not user input

        with self._connect() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(delete_sql, unique_ids)
                deleted = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return deleted

    def get_message(self, message_id: int) -> MessageDetail | None:
        sql = """
            SELECT
                Id,
                ReceivedAt,
                StoredAt,
                CorrelationId,
                SourceSystem,
                ProcessingComponent,
                TargetSystem,
                SessionId,
                RawPayload,
                CONVERT(NVARCHAR(MAX), XmlPayload) AS XmlPayload
            FROM monitoring.Message
            WHERE Id = ?
        """

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (message_id,))
            row = cursor.fetchone()

        if row is None:
            return None

        return MessageDetail(
            id=int(row[0]),
            received_at=row[1],
            stored_at=row[2],
            correlation_id=str(row[3]),
            source_system=str(row[4]),
            processing_component=str(row[5]),
            target_system=str(row[6]) if row[6] is not None else None,
            session_id=str(row[7]),
            raw_payload=str(row[8]),
            xml_payload=str(row[9]) if row[9] is not None else None,
        )
