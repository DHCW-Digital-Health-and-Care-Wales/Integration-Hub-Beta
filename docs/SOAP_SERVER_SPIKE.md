# Spike: SOAP / XML Ingestion Server

> Status: **Spike / discovery** — no implementation yet. This document outlines how a SOAP
> (XML-over-HTTP) receiving container could sit alongside the existing MLLP `hl7_server`.

## Goal

Accept HL7 clinical content delivered as **SOAP XML payloads over HTTP(S)** in addition to the
existing **MLLP/TCP** ingestion path, and publish the resulting messages to Azure Service Bus using
the **same downstream contract** as `hl7_server` (same queues/topics, metadata properties, message
store, event logging and metrics).

The key insight: only the **transport and envelope** differ. Everything after "we have an HL7
message + tracking metadata" should be **reused**, not re-implemented.

## Where it fits

```
                    ┌─────────────────┐
  MLLP/TCP  ───────▶│  hl7_server     │──┐
  (port 2575)       │  (existing)     │  │
                    └─────────────────┘  │   ┌──────────────┐
                                         ├──▶│ pre-*-        │──▶ transformer ──▶ sender ──▶ MPI
                    ┌─────────────────┐  │   │ transform    │
  SOAP/HTTPS ──────▶│  hl7_soap_server│──┘   │ queue/topic  │
  (port 8080)       │  (NEW)          │      └──────────────┘
                    └─────────────────┘
```

Both servers are just **ingress adapters** onto the same Service Bus flow.

## Confirmed payload format — HL7 v2.xml in a SOAP envelope

A sample payload has been provided, and it resolves the biggest open question. The SOAP body
carries an **HL7 v2.xml** message in the `urn:hl7-org:v2xml` namespace — *not* embedded ER7 and
*not* foreign HL7v3/CDA. This is the **best possible outcome**, because the platform already speaks
v2.xml natively.

```xml
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                   xmlns:types="urn:hl7-org:v2xml">
  <SOAP-ENV:Body>
    <types:ADT_A05>
      <types:MSH>
        <types:MSH.1>|</types:MSH.1>
        <types:MSH.2>^~\&amp;</types:MSH.2>
        <types:MSH.3><types:HD.1>328</types:HD.1></types:MSH.3>
        ...
        <types:MSH.9>
          <types:MSG.1>ADT</types:MSG.1>
          <types:MSG.2>A31</types:MSG.2>
          <types:MSG.3>ADT_A05</types:MSG.3>
        </types:MSH.9>
        <types:MSH.10>6774333028472727804z213950</types:MSH.10>
        <types:MSH.12><types:VID.1>2.5</types:VID.1></types:MSH.12>
      </types:MSH>
      <types:EVN>...</types:EVN>
      <types:PID>...</types:PID>
      <types:PD1>...</types:PD1>
      <types:PV1>...</types:PV1>
    </types:ADT_A05>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
```

### Why this de-risks the spike massively

The inner `<types:ADT_A05>` element is the **exact same representation** the platform already uses
end-to-end:

- **Generated** by `convert_er7_to_xml()` (the message store `XmlPayload` is v2.xml — see
  `local/sql-scripts/seed-messages.sql`, which stores `<ns0:ADT_A05 xmlns:ns0="urn:hl7-org:v2xml">`).
- **Validated** by existing flow XSDs under `shared_libs/hl7_validation/.../resources/{phw,pims,paris,wds}/`
  — including `ADT_A05.xsd` in the `urn:hl7-org:v2xml` namespace.
- **Converted back to ER7** by the existing `xml_to_er7()` function in the `hl7_validation` shared lib.

The message in the sample is `ADT^A31^ADT_A05` (MSH-9) — a message type **already handled** by
`hl7_server`'s handler map. Sending app `328` → receiving app `100`, HL7 v2.5.

### The three shapes, for reference

| Shape | Description | Effort | This payload? |
|---|---|---|---|
| 1. Embedded ER7 | Pipe-and-hat string inside a SOAP element | Low | No |
| 2. HL7v3 / CDA | Foreign XML clinical model (`urn:hl7-org:v3`) | High (new mapping) | No |
| **3. HL7 v2.xml** | **v2 message as XML in `urn:hl7-org:v2xml`** | **Low — native reuse** | **✅ Yes** |

**Recommendation for the spike:** unwrap the SOAP envelope, take the `<types:ADT_A05>` element,
and feed it straight into the existing `xml_to_er7()` → validate → store → Service Bus path. No new
HL7 parsing or mapping code is required — only the SOAP transport wrapper and envelope handling.

## Proposed service layout

Mirror the standard service convention from `AGENTS.md` (web service → port **8080**, `uvicorn`
for FastAPI). This is a web service, so it looks more like `buswatch` than `hl7_server`.

```
hl7_soap_server/
├── Dockerfile                     # python:3.13-slim-bookworm + uv, non-root appuser (UID 5678)
├── .dockerignore
├── pyproject.toml                 # ruff + bandit + mypy + pytest; shared_libs as uv sources
├── uv.lock
├── check.sh
├── README.md
└── hl7_soap_server/
    ├── __init__.py
    ├── application.py             # entry point: configure_otel(...) + uvicorn.run(app)
    ├── app_config.py              # env config (reuse hl7_server pattern)
    ├── soap_app.py                # ASGI app: WSDL + SOAP endpoint + /healthz
    ├── soap_envelope.py           # parse SOAP envelope, extract the <types:*> v2.xml element
    ├── soap_fault_builder.py      # build SOAP <Fault> responses (transport-level errors)
    └── message_processor.py       # shared publish logic (xml_to_er7 → validate → store → Service Bus)
```

### Library options (to evaluate in the spike)

| Concern | Option | Notes |
|---|---|---|
| SOAP framework | [`spyne`](https://spyne.io/) | Generates WSDL, decorates service methods; mature but low activity. |
| SOAP framework | Plain **FastAPI** + `lxml` | Full control, no WSDL generation; treat SOAP body as raw XML. Matches existing FastAPI use in `buswatch`. |
| XML parsing | `defusedxml` / `lxml` | Secure parsing (disable DTD/entity resolution — see Security). The shared lib already uses `defusedxml`. |
| v2.xml → ER7 | `xml_to_er7` (existing) | Reuse the `hl7_validation` shared lib — consumes the `<types:ADT_A05>` element directly. |
| Flow XSD validation | existing flow schemas | `validate_xml` / flow `ADT_A05.xsd` in `urn:hl7-org:v2xml` — already present per flow. |

The spike should decide between **spyne** (contract-first WSDL, more "SOAP-native") vs
**FastAPI + lxml** (consistent with the current stack, simpler dependency surface).

## Request handling (confirmed shape — HL7 v2.xml)

1. Receive `POST` with `Content-Type: text/xml` (or `application/soap+xml`) + `SOAPAction` header.
2. Parse the SOAP envelope securely (`defusedxml`/`lxml`, entity resolution disabled).
3. Extract the single v2.xml message element from `SOAP-ENV:Body` (e.g. `<types:ADT_A05>` in the
   `urn:hl7-org:v2xml` namespace).
4. **Convert to ER7** with the existing `xml_to_er7()` shared-lib function — this yields the exact
   same ER7 string the MLLP path already produces.
5. **Hand off to shared processing** — the same steps `GenericHandler.reply()` performs today:
   - `parse_message()` + `HL7Validator.validate()`
   - flow schema validation / XML generation (`validate_and_convert_parsed_message_with_flow_schema`)
   - build tracking metadata (`build_common_properties`, flow property builders)
   - `_send_to_message_store(...)` then `_send_to_service_bus(...)`
6. Return a **SOAP response envelope** containing the HL7 ACK (instead of an MLLP-framed ACK).
7. On failure, return a **SOAP `<Fault>`** with the appropriate NAK/error detail.

> Alternatively, validate the incoming v2.xml **directly** against the existing flow `ADT_A05.xsd`
> before converting to ER7 — the sample is already in the schema's namespace — then `xml_to_er7()`
> only to satisfy the downstream ER7 contract. The spike should pick whichever keeps a single
> validation source of truth.

The refactor opportunity: lift the "have HL7 → publish + ack" body out of `GenericHandler` into a
shared `message_processor` so **both** MLLP and SOAP servers call it. This keeps a single source of
truth for validation, metadata, message store and metrics.

## Configuration

Reuse the `hl7_server` `AppConfig` env-var set verbatim (`SERVICE_BUS_NAMESPACE`,
`EGRESS_QUEUE_NAME`/`EGRESS_TOPIC_NAME`, `EGRESS_SESSION_ID`, `MESSAGE_STORE_QUEUE_NAME`,
`WORKFLOW_ID`, `MICROSERVICE_ID`, `HL7_VALIDATION_FLOW`, etc.) plus HTTP-specific additions:

| Variable | Purpose | Default |
|---|---|---|
| `HTTP_HOST` | Bind address | `0.0.0.0` |
| `HTTP_PORT` | Listen port (HTTPS) | `8443` |
| `SOAP_ACTION` | Expected `SOAPAction` header (optional allow-list) | — |
| `MAX_REQUEST_SIZE_BYTES` | Reject oversized payloads (mirror MLLP size limit) | `1048576` |
| `TLS_CERT_FILE` | PEM server certificate (from the keystore) | — |
| `TLS_KEY_FILE` | PEM private key (from the keystore) | — |
| `TLS_KEY_PASSWORD` | Private-key passphrase (secret — inject via env/Key Vault) | — |

> **TLS terminated in the container.** The reference implementation serves **HTTPS directly using
> SSL backed by a keystore** (server certificate + private key), rather than relying on an ingress
> to terminate TLS. The container therefore needs the server cert/key material at runtime. There is
> still **no client authentication** (no mTLS, no WS-Security, no API key) — the keystore provides
> the *server* identity and encryption only, not caller authorisation.

### Keystore → PEM note

"Keystore" is Java terminology (JKS / PKCS#12). Python servers (`uvicorn`/`gunicorn`) expect **PEM**
files, not a JKS. The spike must decide how the cert material is provisioned:

- If we keep TLS **in the container**: export the keystore to PEM (`openssl`/`keytool` →
  `ssl_certfile` + `ssl_keyfile` for uvicorn), or load a PKCS#12 via an `ssl.SSLContext`. Mount the
  material as a secret (never bake it into the image), mirroring the `ca-certs/` injection pattern.
- If Azure ingress can terminate TLS instead, the container can serve plain HTTP internally and the
  keystore requirement moves to the ingress — simpler, but only if the sender accepts it (some
  senders pin the endpoint's server cert). Confirm during the spike.

Health check: expose `/healthz` — replaces the `TCPHealthCheckServer` used by the MLLP
server, since Container Apps can probe HTTP(S) directly.

## Security considerations (NHS / clinical data)

- **No application authentication — network controls are the *only* caller barrier.** TLS (via the
  keystore) gives encryption and *server* identity, but the caller is **not authenticated**. Anyone
  who can reach the URL and complete the TLS handshake can inject a clinical message. This **must**
  be compensated for at the network layer, and should be explicitly called out for
  information-governance / security sign-off:
  - Restrict ingress to **known source IPs** (allow-list) via Container Apps ingress / NSG /
    Application Gateway / Front Door WAF.
  - Keep the endpoint on a **private network** (private ingress + VNet/private endpoint) so it is
    not exposed to the public internet; require the sender to reach it over the NHS network / VPN /
    private peering.
  - Consider adding a lightweight guard even without full auth (e.g. a required shared header/secret
    or IP pinning) if the source system can support it — raise with the sending team.
- **TLS / keystore**: HTTPS is mandatory for data in transit, served in-container from the keystore
  (server cert + key). Enforce a minimum TLS version (1.2+), protect the private-key passphrase as a
  secret (env/Key Vault, never in the image or repo), and plan for **certificate rotation/expiry**.
- **XXE / entity expansion**: disable DTD loading and external entity resolution when parsing
  (`defusedxml` is already used in the shared lib; ensure `resolve_entities=False`, `no_network=True`,
  `load_dtd=False`). This is the single biggest SOAP risk (OWASP A05 — XML External Entities) and is
  **more important here** because the payload is unauthenticated.
- **Billion-laughs / oversized payloads**: enforce `MAX_REQUEST_SIZE_BYTES` before parsing.
- **Input trust**: treat every message as untrusted — rely on existing flow XSD + HL7 validation to
  reject malformed or unexpected content, and log rejections via `event_logger_lib`.
- **No secrets in code** — Service Bus auth via Managed Identity; TLS key/passphrase via env/Key Vault.

## Open questions for the spike

Each question below is expanded with *why it matters*, *what to find out*, and *how the answer
changes the design*. These are the decisions that determine whether the SOAP server is a thin
transport adapter (days of work) or a new parallel pipeline (weeks of work).

### 1. Which SOAP shape do the source systems actually send? ✅ ANSWERED

- **Answer (from provided sample):** **Shape 3 — HL7 v2.xml** in the `urn:hl7-org:v2xml` namespace,
  wrapped in a standard SOAP 1.1 envelope. See "Confirmed payload format" above.
- **Why this is the best case:** The platform already generates, validates and converts this exact
  format. `xml_to_er7()` and the flow `ADT_A05.xsd` schemas already exist. No new HL7 mapping code.
- **Remaining sub-checks:** Confirm **every** source system / message type uses this same v2.xml
  encoding (the sample is `ADT^A31^ADT_A05`; verify A28/A40/A04/A08 etc. per flow), and confirm the
  `types:` namespace prefix and structure are consistent across senders. Grab one more sample per
  message type to be safe.

### 2. Is a WSDL contract required by the sender?

- **Why it matters:** Some enterprise/integration-engine senders (e.g. BizTalk, Mirth, TIE, Ensemble)
  are **contract-first** — they import a WSDL to generate their client and will not send without one.
  Others just `POST` XML to a URL and a WSDL is optional documentation.
- **What to find out:** Ask the sending team whether they need a published WSDL, and whether they
  expect a specific `targetNamespace`, operation name, and `SOAPAction` value. If an existing
  interface spec exists (common for NHS national systems), the contract may already be dictated.
- **How it changes the design:** WSDL required → favours **`spyne`** (generates WSDL from the
  service definition, contract enforced). WSDL optional → **FastAPI + lxml** treating the body as
  raw XML is simpler and matches the current stack.

### 3. What are the ACK / response semantics?

- **Why it matters:** `AGENTS.md` mandates "send to Service Bus synchronously and return ACK only
  after the send completes". SOAP is request/response, so the caller almost certainly expects a
  **synchronous** result in the HTTP response — but *what* result varies.
- **What to find out:** Does the caller expect the **HL7 ACK (MSA segment)** wrapped in the SOAP
  response body, a simple SOAP acknowledgement, or an HL7v3 accept/application-acknowledgement?
  What should a validation failure or a Service Bus failure return — a SOAP `<Fault>`, an HL7 NAK
  (AE/AR), or an HTTP 5xx? Confirm expected timeout tolerance for the synchronous send.
- **How it changes the design:** Determines the response builder (`soap_fault_builder` vs an
  ACK-in-envelope builder) and error mapping. Must preserve the "ACK only after successful publish"
  rule so we never ACK a message that failed to reach the queue.

### 4. WS-Security / WS-Addressing / MTOM requirements? ✅ ANSWERED

- **Answer:** **None.** The sender uses **HTTPS without authorisation** — no WS-Security header,
  no signing/encryption, no API key. This keeps the container simple: parse the plain SOAP 1.1
  envelope with `defusedxml`/`lxml`; no security-header processing library is needed.
- **Implication:** Favours the **FastAPI + lxml** option (no need for `spyne`/WS-Security tooling).
- **Remaining sub-checks:** Confirm there are also no **WS-Addressing** headers to echo and no
  **MTOM/attachments**. Confirm the sender does not expect any signed response.

### 5. TLS termination point and access-control model? ✅ PARTLY ANSWERED

- **Answer:** Transport is **HTTPS terminated in the container**, served with **SSL backed by a
  keystore** (server certificate + private key). There is **no client authentication** — no mTLS,
  no WS-Security, no API key. The keystore provides encryption and *server* identity only.
- **Design impact:** The container needs the server cert/key at runtime as **PEM** (uvicorn/gunicorn
  don't read a Java keystore directly) — export JKS/PKCS#12 → PEM, or load PKCS#12 via an
  `ssl.SSLContext`. Provision the material as a **secret** (env/Key Vault mount), never in the image.
  Listen on an HTTPS port (e.g. `8443`).
- **Why access still needs attention:** TLS authenticates the *server* to the caller, not the caller
  to us. With no client auth, endpoint security still depends on **network controls** — this is the
  main risk to raise for sign-off (see Security section).
- **What to find out / decide:**
  - Source and format of the keystore, and the **certificate rotation/expiry** process.
  - Minimum TLS version to enforce (1.2+), and whether a specific CA chain is expected by the sender.
  - Keep TLS in-container (as the reference does) **or** offload to Azure ingress? Confirm the sender
    doesn't pin the server certificate before considering ingress termination.
  - Will the endpoint be **private** (VNet/private ingress) or public? Strongly prefer private.
  - Can we apply a **source-IP allow-list** for the sending system(s)?
- **How it changes the design:** In-container TLS adds cert/key handling and secret management to the
  container (mirror the `ca-certs/` injection pattern), plus ingress/network configuration in
  `Integration-Hub-Terraform` for the compensating access controls.

### 6. New flow/queue, or feed an existing flow's pre-transform queue?

- **Why it matters:** Decides Service Bus topology, Terraform changes, and whether existing
  transformers/senders can be reused unchanged. If SOAP carries the *same* clinical messages as an
  existing MLLP flow, it should drop onto the **same** `pre-*-transform` queue and reuse everything
  downstream.
- **What to find out:** Which business flow does the SOAP source map to (PHW, Paris, Chemo, PIMS,
  or a brand-new source)? Are the message types/routing properties identical to an existing flow?
  Does it need its own `EGRESS_SESSION_ID` for replay routing?
- **How it changes the design:** Existing flow → set `EGRESS_QUEUE_NAME`/`EGRESS_TOPIC_NAME` +
  `HL7_VALIDATION_FLOW` to the existing values, **zero** downstream/Terraform change beyond deploying
  the new ingress container. New flow → add a queue, alert thresholds, transformer/sender wiring in
  `Integration-Hub-Terraform`, mirroring the existing flow definitions.

## Recommended spike outcome

A minimal **FastAPI + lxml** container that:

- accepts a SOAP-wrapped ER7 message on `:8080`,
- securely unwraps it,
- calls a **shared** `message_processor` (extracted from `GenericHandler`),
- publishes to a Service Bus queue and returns the HL7 ACK inside a SOAP response,
- proves the downstream contract is identical to the MLLP path.

This validates the "transport adapter" model with the least new code and the most reuse of
existing, already-tested shared libraries.
