# lookup_service

Reference-data lookup service for Integration Hub transformers. Transformers ask it for substitution
values (e.g. MSH-3 code → health board) instead of hardcoding mapping dicts in mapper code.

**Status: Phase 1.5 (persistence, upload, auth).**

- **Storage:** tables live in Cosmos DB. Without `COSMOS_ENDPOINT`, they're served read-only from the
  seed CSVs in the image.
- **Writes:** CSV uploads replace a table, from the GUI or the API. They need the `Lookup.Editor` role.
- **Caching:** lookups go through a per-table TTL cache, or an in-memory snapshot for preloaded tables.
- **Auth:** the lookup API needs an Entra bearer token; the GUI and admin API sit behind Container Apps
  Easy Auth. See [Authentication](#authentication).
- **Not yet built:** the client library and the App Gateway route arrive in Phase 2.

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
ENVIRONMENT=LOCAL LOOKUP_AUTH_DISABLED=true uv run python -m lookup_service.application   # http://localhost:8080
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

## Authentication

Two mechanisms, split by path. `/health/live`, `/health/ready` and `/static/*` need no credentials.

| Callers | Paths | Mechanism |
|---------|-------|-----------|
| Transformers and other services | `/api/v1/lookup*` | Entra **bearer token** (`Authorization: Bearer ...`), validated by the service |
| People using the GUI, and the admin API | everything else (`/`, `/tables/*`, `/upload`, `/api/v1/tables*`) | **Container Apps Easy Auth** (Entra sign-in) in front of the app |

**Bearer tokens (lookup API).** The signature is checked against the tenant's JWKS
(`https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys`, cached, refreshed on an unknown
`kid`), plus the issuer (this tenant, v1 or v2.0 form), the audience (`LOOKUP_AUTH_AUDIENCE`) and the
expiry (60 s clock skew). Only `RS256` is accepted. Failures return `401` with a `WWW-Authenticate:
Bearer` header; a token with no `Lookup.*` role returns `403`. If the JWKS endpoint can't be reached,
the response is `503`, not `401`.

**Easy Auth (GUI and admin API).** Easy Auth overwrites `X-MS-CLIENT-PRINCIPAL` (base64 JSON claims)
and `X-MS-CLIENT-PRINCIPAL-NAME` on every request, so the service trusts them. That is only safe
because **the service is reachable only through Easy Auth**; never expose its port directly with auth
enabled. A missing or malformed principal returns `401`.

**Roles** come from the token's or principal's `roles` claim, as Entra app roles. Each role includes
the ones above it:

| Role | Grants |
|------|--------|
| `Lookup.Reader` | Lookup API; GUI and admin API reads |
| `Lookup.Editor` | Reader, plus CSV upload and `PATCH` table settings (GUI and API) |
| `Lookup.Admin` | Everything `Lookup.Editor` can; reserved for admin-only functions as they arrive |

The user recorded as a table's last uploader is the authenticated principal's name (the Easy Auth
principal name or the token's `preferred_username`/`azp`), never a token.

**CSRF.** Every state-changing GUI form carries a double-submit token: a random `lookup_csrf` cookie
(`SameSite=Lax`, `HttpOnly`; `Secure` and `__Host-` prefixed outside `LOCAL`) must match the hidden
`csrf_token` form field or an `X-CSRF-Token` header, or the request gets `403 csrf_failed`. The admin
API's `POST`/`PATCH` need the same header when called with a session (browser) and are exempt when the
request carries an `Authorization: Bearer` header, because a cross-site request can't set one. The
lookup API is read-only and not subject to CSRF.

**Fail closed.** The service refuses to start (`RuntimeError`) if:

- auth is enabled but `LOOKUP_AUTH_TENANT_ID` or `LOOKUP_AUTH_AUDIENCE` is missing. Terraform omits
  both until the Entra app registration exists, so a deployment before then crash-loops on purpose;
- `LOOKUP_AUTH_DISABLED=true` is set while `ENVIRONMENT` isn't `LOCAL`.

**Local development:** set `LOOKUP_AUTH_DISABLED=true` with `ENVIRONMENT=LOCAL`. No token or Easy
Auth header is needed, every caller is a synthetic `local-dev` principal with `Lookup.Admin`, and the
Compose env file `local/env/lookup/lookup-service.env` already sets it. To exercise auth locally,
leave the flag unset and configure the tenant and audience instead.

Tokens, signing keys and header contents are never logged.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/lookup/{table}?k=<part>[&k=<part>...]` | Lookup with positional key parts, in `key_columns` order. Needs a bearer token |
| `GET` | `/api/v1/lookup/{table}?key.<column>=<part>...` | Lookup with named key parts (preferred for composite keys). Needs a bearer token |
| `GET` | `/api/v1/tables` | Tables with columns, row counts, caching mode, cache stats and last upload |
| `GET` | `/api/v1/tables/{table}` | One table, including key normalisation rules |
| `GET` | `/api/v1/tables/{table}/rows?search=&offset=&limit=` | Rows ordered by key; `search` is a case-insensitive key substring; `limit` ≤ 200 |
| `POST` | `/api/v1/tables/{table}/uploads` | Replace a table from a CSV (multipart); see below |
| `PATCH` | `/api/v1/tables/{table}` | Change `ttl_seconds` (whole seconds, 1 to 7 days; `null` = service default) and/or `preload` without re-uploading; same role and CSRF rules as uploads. The GUI table page offers the same with a seconds/minutes/hours/days unit |
| `GET` | `/health/live` | Liveness (no dependency checks) |
| `GET` | `/health/ready` | Readiness: `200` once tables are loaded and preloaded, otherwise `503` |

```bash
curl 'http://localhost:8090/api/v1/lookup/health_board_mapping?k=224'
# {"table":"health_board_mapping","key":["224"],"value":"VCC","values":{"health_board":"VCC"},"source":"file","cached":true}

curl 'http://localhost:8090/api/v1/lookup/ward_map?key.sending_facility=fac1&key.ward_code=w2'
# key is normalised to ["FAC1","W2"] per the table's key_normalisation rules
```

`value` is the table's `default_value_column`, and `values` holds every value column. `cached` is
`false` only when the row was read from Cosmos for this request. These examples run against the local
Compose service (auth disabled); in a deployed environment add `-H "Authorization: Bearer $TOKEN"`.

Errors use one JSON shape, `{"error": "...", "detail": "...", "table": "..."}`. Upload validation
failures add an `errors` list:

| Situation | Status | `error` |
|-----------|--------|---------|
| Unknown table | `404` | `table_not_found` |
| No row for the key | `404` | `key_not_found` (the key is deliberately not echoed) |
| Missing key, mixed `k=`/`key.` styles, wrong part count, unknown or duplicate part name, empty part | `422` | `invalid_key` |
| Invalid CSV, rows, definition or mapping (nothing is changed) | `422` | `invalid_upload` |
| File over `LOOKUP_MAX_UPLOAD_MB` | `413` | `upload_too_large` |
| Uploads and `PATCH` without `Lookup.Editor` (or a lookup without a `Lookup.*` role) | `403` | `forbidden` |
| Missing or invalid CSRF token | `403` | `csrf_failed` |
| Missing, invalid, expired or wrong-audience token; missing Easy Auth principal | `401` | `unauthorized` |
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
| `ENVIRONMENT` | `DEV` | Swagger exposure (`LOCAL`, `DEV`, `SIT` only); the only environment where `LOOKUP_AUTH_DISABLED` is accepted is `LOCAL` |
| `LOOKUP_AUTH_TENANT_ID` | *(empty)* | Entra tenant whose tokens are accepted; required unless auth is disabled |
| `LOOKUP_AUTH_AUDIENCE` | *(empty)* | Expected token audience, e.g. `api://lookup-service`; required unless auth is disabled |
| `LOOKUP_AUTH_DISABLED` | `false` | `true` turns off bearer-token and Easy Auth checks; **only accepted when `ENVIRONMENT=LOCAL`**, otherwise the service refuses to start |
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
