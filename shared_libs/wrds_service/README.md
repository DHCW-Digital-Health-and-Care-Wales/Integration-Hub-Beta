# WRDS Service

Standalone SOAP client for the WRDS (Welsh Reference Data Service) `GetResultSet` operation, used to
translate coded reference-data values (sex, marital status, religion, ethnicity, title, language)
between code systems.

This package is deliberately **not** part of `shared_libs/` — it is a standalone top-level package,
consumed by `hl7_core_reference_transformer` (and any future consumer) via a `[tool.uv.sources]` path
dependency, the same way `shared_libs/*` packages are consumed. It is unrelated to `soap_sender` /
`soap_subscription_sender`.

## Overview

WRDS exposes a generic `GetResultSet` SOAP operation: callers supply a lookup table name, a list of
filter attribute name/value pairs, and a list of attribute names to retrieve, and get back zero or
more result rows.

For Core Reference translation, the confirmed calling pattern is **one `GetResultSet` call per HL7
message**: filter only on `FromSystem`/`ToSystem` (constant for the whole message), and retrieve
`FromCode`/`type`/`ToCode` for every row in one round trip. Each of the (up to six) coded PID fields in
the message is then translated **client-side**, by filtering the already-fetched rows on `FromCode` +
`type` — no further network calls per field.

## Features

- **Generic `get_result_set()`**: builds a `GetResultSetRequest` SOAP envelope from a lookup table name,
  a list of `(name, value)` filter attributes, and a list of attribute names to retrieve; returns one
  `dict[str, str]` per `<Row>` in the response.
- **Client-side `get_to_code()`**: filters an already-fetched row list by `FromCode` + `type` (no
  network call), matching attribute names case-insensitively (the WRDS response can return the
  requested `type` attribute back as `Type`), and returns `""` if no matching row is found — the same
  outcome as a matching row with an empty `ToCode` value.
- Hand-built SOAP 1.1 envelope + `requests` + `defusedxml.ElementTree` (hardened against malicious XML
  payloads, consistent with `soap_sender`'s response-parsing approach) — no `zeep`/WSDL dependency.

## Usage

```python
from wrds_service import WRDSService

with WRDSService(endpoint_url={WRDS_ENDPOINT_URL}) as wrds:
    rows = wrds.get_result_set(
        lookup_table_name="FioranoCodeTranslation",
        attributes=[("FromSystem", from_system), ("ToSystem", to_system)],
        attributes_to_retrieve=["FromCode", "type", "ToCode"],
        exact_match=True,
    )

    sex_to_code = wrds.get_to_code(rows, from_code=sex_from_code, reference_type="Sex")
    marital_status_to_code = wrds.get_to_code(rows, from_code=marital_status_from_code, reference_type="Marital Status")
```

Raises `WRDSServiceError` on SOAP fault, transport, timeout, or response-parsing failures.

### Local testing without a network call

Pass `fixture_file_path` to read a local file containing a raw SOAP `GetResultSetResponse` body
(e.g. one captured from a real WRDS call) instead of making an HTTP request — useful when the real
WRDS endpoint isn't reachable (e.g. no VPN route from inside a container):

```python
wrds = WRDSService(endpoint_url={WRDS_ENDPOINT_URL}, fixture_file_path="wrds_local_fixture.xml")
rows = wrds.get_result_set(...)  # parses the fixture file, makes no network call
```

`FromSystem`/`ToSystem` filtering is not applied in fixture mode — the whole response is parsed and
returned as-is (callers still filter client-side via `get_to_code()`).

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [wrds_service](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit wrds_service/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports wrds_service/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
