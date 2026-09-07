# HL7 Core Reference Transformer

HL7v2 Core Reference (RISP → MPI) transformer — translates six coded PID fields (Sex, Title,
Language, Marital Status, Religion, Ethnicity) between code systems using the standalone
[`wrds_service`](../shared_libs/wrds_service) SOAP client, and forwards the (otherwise unchanged) message to the
shared MPI sender.

## Features

- **Message-type filter**: only processes ADT `A28`/`A31`/`A40` triggers (defence-in-depth; other
  message types pass through unmodified).
- **In-place field mutation**: parses the message once and mutates only the six target PID fields —
  everything else in the message (segments, field order, `MSH` values, custom segments, etc.) passes
  through byte-for-byte unchanged.
- **Single bulk WRDS lookup per message**: one `GetResultSet` call filtered on `FromSystem`/`ToSystem`
  (from `MSH-3.1`/`MSH-5.1`), retrieving `FromCode`/`type`/`ToCode` for the whole translation table;
  each field is then translated client-side with no further network calls.
- **Empty-value rules**: an empty/HL7-null source field is left untouched (no lookup performed); a
  looked-up field with no matching row, or an empty `ToCode`, is replaced with an empty value.

## Field Mapping

| Field (label) | `type` string | HL7 path (v2.5) | Replacement scope |
|---|---|---|---|
| Sex | `Sex` | `PID-8` | Whole field |
| Title | `Title` | `PID-5.5` | `XPN.5` sub-component only |
| Language | `Language` | `PID-15.1` | `CE.1` component only |
| Marital Status | `Marital Status` | `PID-16.1` | `CE.1` component only |
| Religion | `Religion` | `PID-17.1` | `CE.1` component only |
| Ethnicity | `Ethnicity` | `PID-22.1` | `CE.1` component only |

## Configuration

In addition to the standard transformer env vars (`INGRESS_QUEUE_NAME`, `INGRESS_SESSION_ID`,
`EGRESS_QUEUE_NAME`, `EGRESS_SESSION_ID`, `WORKFLOW_ID`, `MICROSERVICE_ID`, `SERVICE_BUS_CONNECTION_STRING`
or `SERVICE_BUS_NAMESPACE`, `HEALTH_CHECK_HOST`, `HEALTH_CHECK_PORT`), this transformer reads:

| Env var | Purpose | Default |
|---|---|---|
| `WRDS_ENDPOINT_URL` | WRDS SOAP POST endpoint | *(required)* |
| `WRDS_TIMEOUT_SECONDS` | SOAP call timeout, in seconds | `30` |
| `WRDS_CLIENT_CERT_PATH` | Optional PEM client cert path for mTLS | *(none)* |
| `WRDS_LOOKUP_TABLE_NAME` | WRDS `LookupTable` name | `FioranoCodeTranslation` |
| `WRDS_LOCAL_FIXTURE_PATH` | Optional path to a local file containing a raw SOAP `GetResultSetResponse` body (e.g. captured from a real WRDS call). When set, `GetResultSet` parses this file instead of calling WRDS over the network — for local testing only. | *(none)* |

### Local testing without a WRDS connection

If the real WRDS endpoint isn't reachable from your machine/container (e.g. no VPN route), set
`WRDS_LOCAL_FIXTURE_PATH` to a local file containing a raw SOAP `GetResultSetResponse` body, e.g.
captured from a real WRDS call (logged by `WRDSService.get_result_set()` at `INFO` level) or a
hand-authored example:

```xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetResultSetResponse xmlns="http://www.wales.nhs.uk/namespaces/MessageRelease2">
      <Row>
        <AttributeValuePair>
          <Attribute><Id></Id><Name>FromCode</Name><Namespace>http://www.wales.nhs.uk/nrds</Namespace></Attribute>
          <Value>1</Value>
        </AttributeValuePair>
        <AttributeValuePair>
          <Attribute><Id></Id><Name>Type</Name><Namespace>http://www.wales.nhs.uk/nrds</Namespace></Attribute>
          <Value>Sex</Value>
        </AttributeValuePair>
        <AttributeValuePair>
          <Attribute><Id></Id><Name>ToCode</Name><Namespace>http://www.wales.nhs.uk/nrds</Namespace></Attribute>
          <Value>M</Value>
        </AttributeValuePair>
      </Row>
    </GetResultSetResponse>
  </soap:Body>
</soap:Envelope>
```

A starter fixture is checked out at `hl7_core_reference_transformer/wrds_local_fixture.xml` (gitignored
— edit it freely, it will never be committed). `FromSystem`/`ToSystem` filtering is **not** applied in
fixture mode; the whole file is parsed and returned as-is, and each PID field is still filtered
client-side by `FromCode`/`Type` as normal. See `local/core-reference-hl7-transformer.env` for the
commented-out compose wiring.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_core_reference_transformer](.) folder, to create a virtual environment and install project
dependencies:

```bash
uv sync
```

Run code quality checks and unit tests:

```bash
bash check.sh
```
