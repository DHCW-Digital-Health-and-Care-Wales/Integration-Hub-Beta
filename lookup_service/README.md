# lookup_service

Reference-data lookup service for Integration Hub transformers. Transformers ask it for substitution
values (e.g. MSH-3 code → health board) instead of hardcoding mapping dicts in mapper code.

**Status: Phase 1 (persistence + upload).**

- **Storage:** tables live in Cosmos DB. Without `COSMOS_ENDPOINT`, they're served read-only from the
  seed CSVs in the image.
- **Writes:** CSV uploads replace a table, from the GUI or the API.
- **Caching:** lookups go through a per-table TTL cache, or an in-memory snapshot for preloaded tables.
- **Not yet built:** auth, the client library and deployment arrive in Phase 2. Until then, **uploads
  are only allowed when `ENVIRONMENT=LOCAL`**.

## How lookups are served

- **Startup:** every table definition is loaded into memory, so a lookup never reads a definition.
  `/health/ready` passes only after this completes.
- **Seeding:** with Cosmos, any `seed/*.csv` table that doesn't exist there yet is imported first.
  Existing tables are never overwritten.
- **`preload: true` tables:** the whole table is held in memory and served without per-key I/O. Use
  this for small, hot tables such as `health_board_mapping`.
- **Other tables:** each lookup goes cache → Cosmos point read → cache. The TTL is the table's
  `ttl_seconds`, or `LOOKUP_DEFAULT_TTL_SECONDS` if not set.
  - Misses aren't cached yet; negative caching arrives in Phase 4.
- **After an upload:** the table's cache and snapshot are rebuilt **on the replica that handled the
  upload**. Other replicas only see the change in Phase 4 (cross-replica invalidation), so run a
  single replica until then.

## Running locally

With uv (from this directory):

```bash
uv sync
ENVIRONMENT=LOCAL uv run python -m lookup_service.application   # http://localhost:8080
```

With Docker Compose (from `local/`). This also starts the Cosmos emulator; the service restarts until
the emulator is ready, which takes about a minute on first start:

```bash
docker compose --profile lookup up -d --build lookup-service      # http://localhost:8090
```

- GUI:
  - `/`: the table overview;
  - `/tables/<name>`: definition, cache stats, a lookup tester, and searchable, paged rows;
  - `/upload`: replace or create a table from a CSV. The form reads the chosen file's header in the
    browser so you can click to pick key columns.
- Swagger: `/docs`, served only when `ENVIRONMENT` is `LOCAL`, `DEV` or `SIT`.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/lookup/{table}?k=<part>[&k=<part>...]` | Lookup with positional key parts, in `key_columns` order |
| `GET` | `/api/v1/lookup/{table}?key.<column>=<part>...` | Lookup with named key parts (preferred for composite keys) |
| `GET` | `/api/v1/tables` | Tables with columns, row counts, caching mode, cache stats and last upload |
| `GET` | `/api/v1/tables/{table}` | One table, including key normalisation rules |
| `GET` | `/api/v1/tables/{table}/rows?search=&offset=&limit=` | Rows ordered by key; `search` is a case-insensitive key substring; `limit` ≤ 200 |
| `POST` | `/api/v1/tables/{table}/uploads` | Replace a table from a CSV (multipart); see below |
| `GET` | `/health/live` | Liveness (no dependency checks) |
| `GET` | `/health/ready` | Readiness: `200` once tables are loaded and preloaded, otherwise `503` |

```bash
curl 'http://localhost:8090/api/v1/lookup/health_board_mapping?k=224'
# {"table":"health_board_mapping","key":["224"],"value":"VCC","values":{"health_board":"VCC"},"source":"file","cached":true}

curl 'http://localhost:8090/api/v1/lookup/ward_map?key.sending_facility=fac1&key.ward_code=w2'
# key is normalised to ["FAC1","W2"] per the table's key_normalisation rules
```

`value` is the table's `default_value_column`, and `values` holds every value column. `cached` is
`false` only when the row was read from Cosmos for this request.

Errors use one JSON shape, `{"error": "...", "detail": "...", "table": "..."}`. Upload validation
failures add an `errors` list:

| Situation | Status | `error` |
|-----------|--------|---------|
| Unknown table | `404` | `table_not_found` |
| No row for the key | `404` | `key_not_found` (the key is deliberately not echoed) |
| Missing key, mixed `k=`/`key.` styles, wrong part count, unknown or duplicate part name, empty part | `422` | `invalid_key` |
| Invalid CSV, rows, definition or mapping (nothing is changed) | `422` | `invalid_upload` |
| File over `LOOKUP_MAX_UPLOAD_MB` | `413` | `upload_too_large` |
| Uploads when `ENVIRONMENT` isn't `LOCAL` | `403` | `writes_disabled` |
| Uploads to the read-only seed-file store | `409` | `read_only` |
| Tables not loaded yet | `503` | `not_ready` |
| Cosmos unavailable | `503` | `backend_unavailable` |

## Uploading a table

`POST /api/v1/tables/{table}/uploads` takes multipart form fields:

- `file`: the CSV.
- `definition` (optional JSON):
  - required to create a new table;
  - for an existing table, it replaces the definition along with the data;
  - fields are `key_columns`, `value_columns`, `default_value_column`, `key_normalisation`,
    `ttl_seconds`, `preload` and `description`, with the same defaults as the seed manifest.
- `mapping` (optional JSON):
  - maps table columns to CSV columns, with `trim`/`upper`/`lower` transforms, e.g.
    `{"key": {"code": {"path": "Code", "transforms": ["trim"]}}, "values": {"text": {"path": "Text"}}}`;
  - by default, columns are matched by name.

```bash
curl -F file=@reasons.csv \
     -F 'definition={"key_columns": ["code"], "key_normalisation": {"code": {"case": "upper"}}}' \
     http://localhost:8090/api/v1/tables/discharge_reason/uploads
```

- **Validation first:** the whole file is checked before anything is written (header, ragged rows,
  empty or duplicate keys after normalisation, unmapped columns). The response lists up to 50
  problems by line number.
- **Writes:** rows go to Cosmos in transactional batches of up to 100. Rows are upserted before stale
  rows are deleted, so keys present before and after never disappear mid-replace.
- **Not atomic yet:** readers can briefly see a mix of old and new rows. Versioned, atomic replace
  arrives in Phase 3, which is required before PRD.
- **Serialised:** uploads on one replica run one at a time.

## Seed data

Each `seed/<table>.csv` becomes a table:

- the header row is required;
- the file is UTF-8, and a BOM is tolerated;
- blank lines are skipped;
- quoting follows standard CSV rules.

By default, the first column is the key and the rest are values. `seed/tables.json` can override this
per table:

```json
{
  "tables": {
    "ward_map": {
      "description": "...",
      "key_columns": ["sending_facility", "ward_code"],
      "value_columns": ["national_ward_code", "description"],
      "default_value_column": "national_ward_code",
      "key_normalisation": {"ward_code": {"trim": true, "case": "upper"}},
      "ttl_seconds": 600,
      "preload": false
    }
  }
}
```

- Table names must match `[a-z0-9][a-z0-9_-]{0,63}`.
- Column names must match `[A-Za-z_][A-Za-z0-9_]{0,63}`, because they appear in `key.<column>` query
  parameters.
- Key parts are trimmed by default. `case` can be `preserve` (the default), `upper` or `lower`.
  - The same rule applies when loading and when looking up, so `" w2 "` and `"W2"` match if the
    table says so.

Seed data is validated at startup, and **any problem stops the service starting**. This covers:

- duplicate keys (after normalisation);
- empty key parts;
- ragged rows;
- unmapped or missing columns;
- unknown manifest fields;
- manifest entries with no CSV;
- files over 50 MB.

Errors report line numbers, never data values.

The shipped tables are:

- `health_board_mapping`: mirrors `HEALTH_BOARD_MAPPING` in `hl7_chemo_transformer`'s `pid_mapper`;
- `ward_map`: illustrative composite-key data only.

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `LOOKUP_SEED_DIR` | `./seed` (image: `/app/lookup_service/seed`) | Directory of seed CSVs and `tables.json` |
| `ENVIRONMENT` | `DEV` | Swagger exposure; uploads are only allowed in `LOCAL` until Phase 2 auth |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | Bind address |
| `LOG_LEVEL` | `INFO` | Log level |
| `AZURE_LOG_LEVEL` | `WARNING` | Azure SDK log level; keep at WARNING or above, because SDK HTTP logs include Cosmos URLs that contain lookup keys |
| `COSMOS_ENDPOINT` | *(empty)* | Cosmos account URI; empty = read-only seed-file store |
| `COSMOS_KEY` | *(empty)* | Set for the emulator (key auth, auto-creates database and containers); empty = `DefaultAzureCredential`, with Terraform-provisioned containers |
| `COSMOS_DATABASE` | `integration-hub` | Database (shared with the dashboard) |
| `COSMOS_DISABLE_SSL_VERIFY` | `false` | `true` only for the emulator; refused at startup for any other endpoint |
| `LOOKUP_ROWS_CONTAINER` / `LOOKUP_CONFIG_CONTAINER` | `lookup-rows` / `lookup-config` | Containers (partition keys `/table_name` and `/pk`) |
| `LOOKUP_DEFAULT_TTL_SECONDS` | `300` | Cache TTL for tables without `ttl_seconds` |
| `LOOKUP_CACHE_MAX_ENTRIES` | `10000` | Max cached rows per TTL table |
| `LOOKUP_MAX_UPLOAD_MB` | `50` | Upload size limit |
| `LOOKUP_UPLOAD_CONCURRENCY` | `32` | Concurrent Cosmos batch requests during an upload |

Uvicorn access logging is **disabled**. Lookup keys travel in the query string, and keys and values
must not be logged.

## Development

```bash
bash check.sh                                   # ruff, bandit, mypy (source + tests), unit tests
uv run python -m unittest discover tests        # tests only

# Opt-in Cosmos integration tests against the emulator (throwaway database, deleted afterwards)
LOOKUP_IT_COSMOS_ENDPOINT=https://localhost:8081 LOOKUP_IT_COSMOS_KEY='<emulator key>' \
  uv run python -m unittest tests.test_cosmos_store
```

## Phase 1 acceptance (2026-10-05, Cosmos emulator, Apple Silicon laptop)

- **100k rows through the GUI:** a 100,000-row CSV uploaded via `/upload` created `big_codes`.
  Replacing it with a shifted 100k-row file (5k removed, 5k new) took **92 s**. The new data was
  served immediately, and removed keys returned `404`.
- **Throughput on the emulator:**
  - transactional batches wrote ~5.6× faster than per-row upserts (10k rows: 3.4 s vs 19.1 s);
  - 1000-item query pages listed ids ~8× faster than the SDK default page size;
  - real Cosmos throughput depends on provisioned RU/s.
- **Cache:** a repeat lookup returned `cached: true`, and table cache stats showed the hit, with no
  second Cosmos read. Unit tests assert the store call count.
- **Restart:** after `docker restart lookup-service`, uploaded data was still served, and the
  preloaded `health_board_mapping` served as soon as `/health/ready` passed.

## Latency (Phase 0 acceptance)

`scripts/latency_check.py` sends sequential keep-alive GETs and reports client-observed percentiles,
which is an upper bound on service-side latency:

```bash
uv run python scripts/latency_check.py --url http://localhost:8090 --requests 5000
```

Measured on 2026-10-05 against the Compose container (Docker Desktop, Apple Silicon laptop), 5,000
mixed single and composite-key hits:

| p50 | p95 | p99 | max | throughput (sequential) |
|-----|-----|-----|-----|-------------------------|
| 0.53 ms | 0.98 ms | 3.22 ms | 14.18 ms | ~1,550 req/s |

The p99 is under the 5 ms target, including Docker Desktop port-forwarding overhead.
