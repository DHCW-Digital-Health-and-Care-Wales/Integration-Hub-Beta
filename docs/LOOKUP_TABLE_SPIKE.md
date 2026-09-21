# Spike: Value Lookup Tables for Transformers

> Status: **Spike / discovery** — no implementation yet. This document evaluates options for
> giving transformers a shared way to look up substitution values, per `Notes/lookup_table_spec.md`.

## Requirement (from spec)

- Transformers need to look up values to perform substitutions in messages.
- Different lookup data is required for different flows.
- Part of the lookup key determines the dataset / lookup table name.
- A single flow could use more than one lookup table.
- Some lookup data is small and could be added at compile time.
- Some lookup data could be larger and may be better stored in Cosmos DB.
- Lookup calls must be thread safe.
- Calls that get data from Cosmos DB should be cached.

## Background: current state

There is no shared lookup abstraction today. Each transformer (`hl7_phw_transformer`,
`hl7_chemo_transformer`, `hl7_pims_transformer`, `xml_fhir_proms_transformer`) subclasses
`BaseTransformer` (`shared_libs/transformer_base_lib`) and implements `transform_message()` by
calling a set of per-segment mapper functions (e.g. `mappers/pid_mapper.py`, `mappers/msh_mapper.py`),
which use `field_utils_lib` helpers (`get_hl7_field_value`, `set_nested_field`,
`copy_segment_fields_in_range`) to move/transform HL7 fields.

The only existing precedent for a "lookup table" is a **hardcoded module-level dict** in
`transformers/hl7_chemo_transformer/hl7_chemo_transformer/mappers/pid_mapper.py`:

```python
HEALTH_BOARD_MAPPING = {
    "224": "VCC",
    "212": "BCUCC",
    "192": "SWWCC",
    "245": "SEWCC",
}
...
health_board = HEALTH_BOARD_MAPPING.get(msh3_value, "")
```

This is exactly the "small, compile-time" case from the spec, but it's private to one mapper file
and not reusable across transformers or flows.

There is also an existing Cosmos DB integration pattern in the codebase — not for transformers, but
for the NOC dashboard's alarm persistence (`dashboard/dashboard/services/cosmos_store.py`), which
establishes conventions worth reusing:

- A single `CosmosClient` is created lazily and kept as a **process-wide singleton**, guarded by a
  `threading.Lock` (double-checked locking on `_client_cache["client"]`).
- Dual auth mode: `COSMOS_KEY` set → key auth + auto-create DB/container (local/emulator); key
  unset → `DefaultAzureCredential`/Managed Identity RBAC, assuming DB/container already exist
  (provisioned via Terraform) — data-plane roles can't create containers.
- Graceful degradation: if Cosmos isn't configured, reads return `None`/empty rather than raising,
  and errors are logged and swallowed.

This is a strong template for a lookup provider's Cosmos backend, but it has **no caching layer** —
every `get_document()` call hits Cosmos. The spec explicitly requires caching for Cosmos-backed
lookups, so that part needs to be added new.

No existing code in `shared_libs/` or the transformers uses `functools.lru_cache`, `cachetools`, or
a TTL cache (checked across non-`.venv` source). `threading.Lock`/`RLock` usage is limited to the
dashboard's Cosmos client singleton and a lock used in a `message_bus_lib` test. So there's no
existing shared caching utility to reuse as-is — this would be a new addition.

## Where lookups fit in the transformer pipeline

Mappers are plain functions called synchronously inside `transform_message()`, per message, per
flow. Per the server component rules (`.github/copilot-instructions.md`), transformers must **not**
introduce thread pools or async processing — but `processor_manager_lib`/`message_bus_lib` may still
process sessions concurrently across worker threads, so any lookup mechanism must tolerate
concurrent calls safely even though each individual transformer instance processes one message at a
time.

A lookup call would sit inside a mapper, e.g.:

```python
value = lookup_service.get("health_board_mapping", msh3_value, default="")
```

## Design options

### Option A — Compile-time constant dict (status quo, generalised)

Plain Python `dict` literals, one module per table, importable by any transformer.

- **Pros**: zero latency, zero external dependency, trivially thread safe (read-only), easy to
  code-review and version alongside the transformer logic.
- **Cons**: requires a code change + deployment to update data; not suitable for large or
  frequently-changing datasets; duplicated per-flow unless centralised.
- **Fit**: small, stable, flow-specific tables (e.g. `HEALTH_BOARD_MAPPING`).

### Option B — Packaged config file (JSON/YAML/INI shipped in the container image)

Similar to the existing `config.ini` pattern (`transformer_base_lib.app_config.TransformerConfig`),
but for lookup data — e.g. `lookup_tables/health_board_mapping.json` loaded once at import/startup
into an in-memory dict.

- **Pros**: keeps data out of code (easier to diff/review as data, not logic), still no runtime
  dependency, no thread-safety concerns once loaded (immutable after load), still versioned with the
  deployed image.
- **Cons**: still requires a rebuild/redeploy to change; not suitable for large datasets; adds a
  small startup cost to parse the file.
- **Fit**: medium-sized, still-static tables that change more often than code but don't need to
  change without a deploy.

### Option C — Cosmos DB–backed lookup, cached

For larger or dynamically-updatable datasets. Reuses the dashboard's Cosmos client conventions
(singleton client, lazy init, key-vs-RBAC dual auth) but adds a caching layer, since the spec
requires Cosmos-sourced values to be cached, and diverges from the dashboard on error handling (see
[Failure handling](#failure-handling-retry-then-hard-failure) below).

- **Data model**: **reuse the existing dashboard Cosmos account** (`module.noc_dashboard_cosmos` in
  `Integration-Hub-Terraform/components/app-platform/cosmosdb.tf`) rather than provisioning a new
  Cosmos account per environment — see
  [Infrastructure: reuse the dashboard's Cosmos account](#infrastructure-reuse-the-dashboards-cosmos-account)
  below. Add a new `lookups` container to that account (alongside the existing `dashboard` container),
  partitioned by `table_name` with `id` = lookup key, so a table name + key resolves to a
  single-partition point read — same low-cost pattern as the alarm store. Some tables need a
  **composite key** (more than one field combining to identify a row) — see
  [Composite keys](#composite-keys) below for how that's handled without leaking into mapper code.
- **Caching**: an in-process TTL cache keyed by `(table_name, key)`, with the **TTL configurable per
  table** (see the env var table below) since some tables may tolerate longer staleness than others.
  `functools.lru_cache` was considered but rejected as the sole mechanism — it has no TTL/invalidation,
  so a stale value would persist for the container's lifetime.
- **Thread safety**: same double-checked-locking approach as `cosmos_store._get_client()` for the
  singleton client; cache reads/writes guarded by a lock (or a thread-safe cache implementation) so
  concurrent mapper calls (across worker threads, if introduced later) can't race on cache population.
- **Pros**: supports large/changeable datasets without redeploying; centrally managed data; reusing
  the dashboard's account avoids provisioning and paying for a second Cosmos account.
- **Cons**: new runtime dependency (`azure-cosmos`, already used by `dashboard`); couples the lookup
  feature's availability to the dashboard Cosmos account's lifecycle (`deploy_noc_dashboard_cosmos`)
  unless that variable is renamed/generalised; a Cosmos failure is a **hard failure for message
  processing**, not a silent fallback (unlike the dashboard's graceful degradation — see below).
- **Fit**: larger, less static, or shared-across-flows lookup data.

## Proposed shared abstraction

Introduce a single `lookup_service_lib` (or extend `field_utils_lib`) shared library exposing one
interface so mapper code doesn't need to know which backend serves a given table:

```python
LookupKey = str | tuple[str, ...]


class LookupProvider(Protocol):
    def get(self, table_name: str, key: LookupKey, default: str | None = None) -> str | None: ...
```

with two implementations composed behind it:

- `StaticLookupProvider` — wraps Option A/B (in-memory dict, loaded at import/startup).
- `CosmosLookupProvider` — wraps Option C (Cosmos read + TTL cache + lock), following the
  `cosmos_store.py` singleton/auth/degradation conventions.

A thin `CompositeLookupProvider` (or per-flow registry) can route a `table_name` to the right
backend, since the spec notes a flow could use more than one table and tables can be a mix of
static and Cosmos-backed. `get()` is documented as being able to raise `LookupBackendError` for
**any** table — the static provider simply never does in practice — so mapper code written against
a static table doesn't silently assume that safety carries over if the table is later moved to
Cosmos. See [Is the hybrid approach clean?](#is-the-hybridstaticcosmos-approach-clean) below.

## Composite keys

**Requirement**: some tables are keyed by a single value (e.g. `HEALTH_BOARD_MAPPING`'s
`msh3_value`), but others may need more than one field to identify a row (e.g. sending facility +
local code). The `key` parameter above accepts a plain `str` **or** a `tuple[str, ...]` so this is
handled without pushing key-composition logic into every mapper:

- **Callers**: pass whatever's natural — `lookup.get("health_board_mapping", msh3_value)` for a
  single-value key, or `lookup.get("ward_health_board", (sending_facility, ward_code))` for a
  composite one. Mappers never build a delimited string themselves.
- **`StaticLookupProvider`**: needs no extra work — Python dicts natively support tuple keys, so a
  composite-keyed static table is just `{("224", "M"): "VCC-M", ...}`.
- **`CosmosLookupProvider`**: is the **one place** that turns a tuple into a Cosmos document `id`
  (Cosmos ids disallow `/`, `\`, `?`, and `#`, so the join delimiter must avoid those — `::` is
  proposed, since HL7 itself already uses `|`, `^`, `~`, and `\` as its own segment/field/repetition/
  escape delimiters and reusing one of those as our delimiter would be confusing next to real HL7
  values). Each part is trimmed before joining; case-folding is left as a per-table concern rather
  than a blanket rule, since not all reference codes are case-insensitive.
- **Caching**: the tuple is used directly as (part of) the in-process cache key
  (`(table_name, key)`) — tuples are hashable, so composite keys need no special-casing in the TTL
  cache either. A plain string key is just the one-part case of the same mechanism.
- **Debuggability trade-off**: a composed `id` (e.g. `224::M`) is less immediately readable in the
  Cosmos Data Explorer than separate fields. Worth also storing the individual key parts as extra
  fields on the document (cheap, and doesn't affect the point-read), purely for humans querying/
  auditing the container directly.

## Is the hybrid (static + Cosmos) approach clean?

It's the right *shape* for the requirement — small/stable data and large/changeable data genuinely
behave differently, and a single backend would be worse either way — but the single `LookupProvider`
interface doesn't make the split fully transparent. Costs worth naming explicitly rather than
glossing over:

1. **Failure semantics differ by backend.** Static lookups can never fail at runtime (in-memory
   dict, already validated at deploy time); Cosmos lookups can, and per the retry-then-hard-fail
   decision, that means an exception. A mapper written against a table that's static today could
   start raising if that table is ever migrated to Cosmos. Mitigated by documenting `get()` as being
   able to raise `LookupBackendError` regardless of backend (see above), rather than presenting the
   interface as fully backend-agnostic.
2. **Config surface** (`LOOKUP_COSMOS_TABLES`, `LOOKUP_COSMOS_*`, per-table TTL/retry overrides) is
   more moving, stringly-typed parts than today's actual usage (one static table) strictly needs.
   Mitigated by inverting the registry: only list the Cosmos exceptions
   (`LOOKUP_COSMOS_TABLES`), not every table's backend — already reflected in the env var table
   above — plus a startup check that rejects a table name declared both as a static provider in
   code and in `LOOKUP_COSMOS_TABLES`.
3. **Two on-call mental models per table** — "check the code" vs "check Cosmos + RBAC + cache/TTL"
   — with no single discoverable place saying which table is which, other than env vars/tfvars.
   Worth a small in-repo registry/README table mapping table name → backend once tables exist beyond
   `HEALTH_BOARD_MAPPING`.
4. **Testing doubles** for any Cosmos-backed table: retry/TTL/failure-path tests are needed in
   addition to the static happy-path test.

None of these are blockers — they're the normal cost of two backends behind one interface — but the
interface should not be sold as 100% transparent to callers.

## Configuration: environment variables (Terraform-compatible)

**Decision:** routing/backend configuration is read from **environment variables only** — no
`config.ini`/JSON file for wiring (static *table data* can still ship as a packaged file per Option
B; this is about which backend serves a table and how to reach Cosmos). This matches two existing
conventions in the codebase that are both already deployed via Terraform:

- `transformer_base_lib.app_config.AppConfig.read_env_config()` — every transformer already reads
  its Service Bus/queue/workflow config purely from `os.getenv(...)`, with required-vs-optional
  validation (`_read_env`, `_read_int_env`). New lookup settings should follow the same helper
  pattern in `shared_libs`.
- The dashboard's Cosmos config in `dashboard/dashboard/config.py` — `COSMOS_ENDPOINT`,
  `COSMOS_KEY`, `COSMOS_DATABASE`, `COSMOS_CONTAINER`, `COSMOS_DISABLE_SSL_VERIFY` are all plain env
  vars, each wired through Terraform as a Container App environment variable
  (`components/app-platform`, `modules/terraform-azurerm-container-app`'s `environment_variables`
  list of `{name, value}` objects) and set per environment in `environments/app-platform-<env>.tfvars`
  (e.g. `deploy_noc_dashboard_cosmos`, plus the RBAC principal IDs for Cosmos data access).

Proposed variables for the lookup provider, following those naming/shape conventions:

| Env var | Purpose | Example |
|---|---|---|
| `LOOKUP_COSMOS_TABLES` | Comma-separated list of table names backed by Cosmos; **any table not listed defaults to static**. Inverted from an earlier `table:backend` pair design (see [Is the hybrid approach clean?](#is-the-hybridstaticcosmos-approach-clean)) so only the exception needs configuring | `discharge_reason,ward_code` |
| `LOOKUP_COSMOS_ENDPOINT` | Cosmos account URI; empty disables the Cosmos backend (static-only) | `https://uks-dhcw-ih-lookup-cosmos...` |
| `LOOKUP_COSMOS_KEY` | Set for local/emulator key auth; empty → `DefaultAzureCredential`/Managed Identity RBAC, same dual-mode as `cosmos_store.py` | *(empty in cloud envs)* |
| `LOOKUP_COSMOS_DATABASE` / `LOOKUP_COSMOS_CONTAINER` | Database/container names — **same database as the dashboard, new `lookups` container** | `integration-hub` / `lookups` |
| `LOOKUP_CACHE_TTL_SECONDS` | **Default** cache TTL (seconds) for Cosmos-backed reads, used when no per-table override is set | `300` |
| `LOOKUP_CACHE_TTL_SECONDS__<TABLE_NAME>` | Per-table TTL override (table name upper-cased, non-alphanumerics → `_`), read the same way `ENVIRONMENT_COLOR_MAP`-style per-key overrides are handled elsewhere in the codebase | `LOOKUP_CACHE_TTL_SECONDS__DISCHARGE_REASON=3600` |
| `LOOKUP_COSMOS_MAX_RETRIES` | Retries for a transient Cosmos read failure before treating it as a hard failure | `3` |
| `LOOKUP_COSMOS_RETRY_BACKOFF_SECONDS` | Backoff between retries (mirrors the dashboard's `ALERT_EMAIL_RETRY_BACKOFF_SECONDS` pattern for ACS throttling) | `2` |

All values are **plain strings** (no nested structures) so they map directly onto Terraform's
`environment_variables = list(object({ name = string, value = string }))` variable already used by
`terraform-azurerm-container-app`, and onto per-environment `*.tfvars` files — no changes needed to
the module itself, only new component variables (in `components/app-platform/variables.tf`) and
tfvars entries per environment, exactly as was done for the dashboard's `COSMOS_*` and
`dashboard_alert_email_*` variables in `Integration-Hub-Terraform`.

## Infrastructure: reuse the dashboard's Cosmos account

**Decision:** the lookup feature reuses the **same Cosmos account** already provisioned for the NOC
dashboard (`module.noc_dashboard_cosmos` in `components/app-platform/cosmosdb.tf`), rather than
provisioning a second account. Concretely:

- Add a `lookups` entry to that module's `containers` map (alongside the existing `dashboard`
  container), e.g. `lookups = { name = "lookups", partition_key_path = "/table_name" }`. No new
  `azurerm_cosmosdb_account` resource, module call, or private endpoint is needed.
- `LOOKUP_COSMOS_ENDPOINT`/`LOOKUP_COSMOS_DATABASE` are therefore set to the **same values** as the
  dashboard's `COSMOS_ENDPOINT`/`COSMOS_DATABASE`; only `LOOKUP_COSMOS_CONTAINER` differs.
- Each transformer's managed identity is granted **`data_reader_principal_ids`** (not
  `data_contributor_principal_ids`) on the account — transformers only read lookup data, unlike the
  dashboard which needs read/write for alarm state. The `terraform-azurerm-cosmosdb` module already
  supports this role separately.
- The account's `local_authentication_disabled = true` setting (AAD-only in the cloud) is unaffected;
  transformers authenticate the same way the dashboard does — `DefaultAzureCredential`/Managed
  Identity in the cloud, the well-known emulator key locally.
- **Trade-off to flag for follow-up**: this couples the lookup feature's availability to
  `deploy_noc_dashboard_cosmos` and the dashboard's account lifecycle. If the dashboard Cosmos
  account is ever disabled/removed independently of the lookup feature, that variable (and the
  account name) should be generalised/renamed to reflect the shared purpose rather than implying
  it's dashboard-only.

## Failure handling: retry, then hard failure

**Decision:** unlike the dashboard's graceful-degradation philosophy (swallow errors, return
empty/default so the UI still renders), a Cosmos read failure in a transformer is **not** silently
defaulted. HL7 messages carry clinical data, so a silent missing/wrong substitution is worse than
failing loudly:

1. Retry the Cosmos read on transient failures (throttling, timeouts) up to
   `LOOKUP_COSMOS_MAX_RETRIES` times with `LOOKUP_COSMOS_RETRY_BACKOFF_SECONDS` backoff — mirroring
   the retry-with-backoff pattern already used for ACS email throttling
   (`dashboard.services.email_service`, `ALERT_EMAIL_MAX_RETRIES`/`ALERT_EMAIL_RETRY_BACKOFF_SECONDS`).
2. If retries are exhausted, raise rather than defaulting — letting the existing message processing
   retry/error-handling in `processor_manager_lib`/`message_bus_lib` (dead-lettering, redelivery)
   handle it the same way any other transformation failure is handled today.
3. A genuine **key-not-found** (the Cosmos read succeeds but no document matches) is a distinct case
   from a **read failure**, and is out of scope for this decision — still open, see open question 3
   below.

## Open questions (for follow-up spike/design work)

1. ~~Where should table-name → backend routing be configured?~~ **Resolved**: environment
   variables, per the [Configuration](#configuration-environment-variables-terraform-compatible)
   section above.
2. ~~What TTL is appropriate, and should it be configurable per table?~~ **Resolved**: yes, per-table
   via `LOOKUP_CACHE_TTL_SECONDS__<TABLE_NAME>`, falling back to the global `LOOKUP_CACHE_TTL_SECONDS`.
3. ~~Does a Cosmos failure need to be a hard failure vs. soft default?~~ **Resolved for read
   failures**: retry then hard failure, per
   [Failure handling](#failure-handling-retry-then-hard-failure) above. **Still open**: whether a
   genuine key-not-found (data simply absent from the table) should also hard-fail, or fall back to
   a soft default/no-substitution — this may need to be a per-table setting rather than one global
   rule, and ties into whether lookup substitutions should appear in `get_processed_audit_text`
   (e.g. `PhwTransformer`'s existing datetime/DoD transformation reporting).
4. ~~Which Cosmos account/container layout?~~ **Resolved**: reuse the dashboard's existing account,
   new `lookups` container partitioned by `table_name`, per
   [Infrastructure](#infrastructure-reuse-the-dashboards-cosmos-account) above.
5. New dependency choice for the cache implementation: **still undecided**. Leaning towards
   `cachetools.TTLCache` (one new dependency, but per-table TTLs and eviction are handled for free)
   over a hand-rolled `dict` + timestamp + lock, since per-table TTL and the retry logic above add
   enough complexity that reinventing a TTL cache has less value than usual — but this should be
   confirmed against `pyproject.toml` dependency policy ("avoid adding new dependencies unless there
   is a clear, documented need") before implementation.

## Recommendation

- Use **Option A/B (static)** as the default for small, stable tables — this covers today's only
  real example (`HEALTH_BOARD_MAPPING`) and needs no new infrastructure.
- Add **Option C (Cosmos + cache)** as an opt-in backend behind the same `LookupProvider` interface
  for tables that are large or need to change without a redeploy, reusing the **dashboard's existing
  Cosmos account** (new `lookups` container, read-only RBAC for transformers) rather than
  provisioning a new one.
- Cache reads with a **per-table configurable TTL**, and treat a Cosmos read failure as **retry then
  hard failure** rather than a silent default, since HL7 message correctness takes priority over
  availability here — a deliberate divergence from the dashboard's graceful-degradation approach.
- Build this as a new shared lib so all transformers (not just one flow) can adopt it incrementally,
  starting by migrating `HEALTH_BOARD_MAPPING` to the static provider as a proof of concept.
- Configure backend routing and Cosmos connection details entirely via **environment variables**
  (`LOOKUP_TABLE_BACKENDS`, `LOOKUP_COSMOS_*`), read using the same `AppConfig`-style helpers
  transformers already use, and wired in by Terraform's existing `environment_variables` container
  app pattern — no new config file format to support in either the app or the infrastructure repo.
