# lookup_service

Reference-data lookup service for Integration Hub transformers. Transformers ask it for substitution
values (e.g. MSH-3 code → health board) instead of hardcoding mapping dicts in mapper code.

**Status: Phase 0 (POC).** It serves read-only lookups from CSV files baked into the image, with a
status page. There's no Cosmos, upload, cache, auth or client library yet. Those arrive in later
phases of the lookup service build plan.

## Running locally

With uv (from this directory):

```bash
uv sync
ENVIRONMENT=LOCAL uv run python -m lookup_service.application   # http://localhost:8080
```

With Docker Compose (from `local/`):

```bash
docker compose --profile lookup up -d --build lookup-service      # http://localhost:8090
```

- GUI: `/`, the table overview with a per-table lookup tester.
- Swagger: `/docs`, served only when `ENVIRONMENT` is `LOCAL`, `DEV` or `SIT`.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/lookup/{table}?k=<part>[&k=<part>...]` | Lookup with positional key parts, in `key_columns` order |
| `GET` | `/api/v1/lookup/{table}?key.<column>=<part>...` | Lookup with named key parts (preferred for composite keys) |
| `GET` | `/api/v1/tables` | Tables with key/value columns, row counts and load time |
| `GET` | `/health/live` | Liveness (no dependency checks) |
| `GET` | `/health/ready` | Readiness: `200` once tables are loaded, otherwise `503` |

```bash
curl 'http://localhost:8090/api/v1/lookup/health_board_mapping?k=224'
# {"table":"health_board_mapping","key":["224"],"value":"VCC","values":{"health_board":"VCC"},"source":"file","cached":true}

curl 'http://localhost:8090/api/v1/lookup/ward_map?key.sending_facility=fac1&key.ward_code=w2'
# key is normalised to ["FAC1","W2"] per the table's key_normalisation rules
```

`value` is the table's `default_value_column`, and `values` holds every value column.

Errors use one JSON shape, `{"error": "...", "detail": "...", "table": "..."}`:

| Situation | Status | `error` |
|-----------|--------|---------|
| Unknown table | `404` | `table_not_found` |
| No row for the key | `404` | `key_not_found` (the key is deliberately not echoed) |
| Missing key, mixed `k=`/`key.` styles, wrong part count, unknown or duplicate part name, empty part | `422` | `invalid_key` |
| Tables not loaded yet | `503` | `not_ready` |

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
      "key_normalisation": {"ward_code": {"trim": true, "case": "upper"}}
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
| `ENVIRONMENT` | `DEV` | Controls Swagger exposure |
| `HOST` / `PORT` | `0.0.0.0` / `8080` | Bind address |
| `LOG_LEVEL` | `INFO` | Log level |

Uvicorn access logging is **disabled**. Lookup keys travel in the query string, and keys and values
must not be logged.

## Development

```bash
bash check.sh                                   # ruff, bandit, mypy (source + tests), unit tests
uv run python -m unittest discover tests        # tests only
```

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
