"""HTTP client for the PIMS -> MPI reference-data (WRDS/WRRS-style) lookup REST API.

The SBU PIMS ADT Mapping Document requires that certain PID fields are *enriched* before the
message is forwarded to the eMPI - the source code carried by PIMS (HL7 v2.3.1) is replaced with
the code the eMPI expects:

    | eMPI field | PID path       | Dataset       |
    |------------|----------------|---------------|
    | Gender     | PID.8          | gender        |
    | Marital    | PID.16.CE.1    | marital-status|
    | Ethnicity  | PID.22.CE.1    | ethnic-group  |
    | NHS status | PID.32         | nhs-status    |

The authoritative mapping data lives behind a dedicated reference-data REST API (built separately).
This module is the client the transformer uses to resolve each source code to its target code.

Failure handling (see the user story's "Scenario 2 - Format unexpected and invalid"): any failure
to resolve a code - the API being unreachable, a non-2xx response, a missing mapping, or a target
code returned in an unexpected format - raises :class:`ReferenceDataLookupError`, which is a
``ValueError`` subclass. The transformer pipeline (``transformer_base_lib.message_processor``)
catches ``ValueError``, logs the failure *with the message content* to the monitoring solution, and
does **not** acknowledge the message, so it (and every subsequent message on the FIFO session) stays
queued until the problem is resolved.
"""

from __future__ import annotations

import json
import logging
import os
import re
from enum import Enum
from typing import Optional
from urllib.parse import quote

import urllib3
from urllib3.util.retry import Retry
from urllib3.util.timeout import Timeout

logger = logging.getLogger(__name__)

# Default client tuning. Kept small because the lookup is on the synchronous message-processing
# path - a slow reference-data API must not stall the FIFO session indefinitely.
_DEFAULT_TIMEOUT_SECONDS = 5.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BACKOFF_SECONDS = 0.5

# Transient HTTP statuses worth retrying (the API is briefly unavailable / rate limited).
_RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})


class ReferenceDataLookupError(ValueError):
    """Raised when a reference-data code cannot be resolved to a valid target code.

    Subclasses ``ValueError`` so that ``transformer_base_lib.message_processor.process_message``
    treats it as a transformation failure: the message content is logged to the monitoring
    solution and the message is left on the queue (not acknowledged).
    """


class ReferenceDataset(Enum):
    """A reference-data table exposed by the lookup API.

    Each member carries:

    * ``path`` - the URL path segment identifying the dataset in the REST API.
    * ``pattern`` - the format the resolved *target* code must match. The eMPI rejects malformed
      codes, so a value that does not match is treated as "returned in the incorrect format"
      (user story Scenario 2) and raises :class:`ReferenceDataLookupError`.

    The patterns below reflect the NHS/HL7 code systems the eMPI expects: short, delimiter-free
    tokens. They intentionally reject HL7 delimiter characters (``| ^ ~ \\ &``), whitespace and
    over-long values - the kinds of malformed output Scenario 2 guards against.
    """

    GENDER = ("gender", re.compile(r"^[A-Za-z0-9]{1,3}$"))
    MARITAL_STATUS = ("marital-status", re.compile(r"^[A-Za-z0-9]{1,4}$"))
    ETHNIC_GROUP = ("ethnic-group", re.compile(r"^[A-Za-z0-9]{1,4}$"))
    NHS_STATUS = ("nhs-status", re.compile(r"^[0-9]{1,2}$"))

    def __init__(self, path: str, pattern: re.Pattern[str]) -> None:
        self.path = path
        self.pattern = pattern


class ReferenceDataLookupClient:
    """Resolves PIMS source codes to eMPI target codes via the reference-data REST API.

    The client is thread-safe (``urllib3.PoolManager`` is thread-safe) and is intended to be
    created once per process and reused for every message.

    REST contract (served by the separately-built reference-data API):

        GET {base_url}/lookup/{dataset}/{source_code}
            200 -> {"dataset": "...", "sourceCode": "...", "targetCode": "..."}
            404 -> mapping not found
            5xx -> transient server error (retried)
    """

    def __init__(
        self,
        base_url: Optional[str],
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = _DEFAULT_RETRY_BACKOFF_SECONDS,
        api_key: Optional[str] = None,
        http: Optional[urllib3.PoolManager] = None,
    ) -> None:
        # Normalise once; an empty base URL is permitted at construction (keeps the transformer
        # import-safe and constructible in tests) but any actual lookup then fails fast.
        self._base_url = (base_url or "").rstrip("/")
        self._timeout = Timeout(total=timeout_seconds)
        self._api_key = api_key or None

        if http is not None:
            self._http = http
        else:
            retry = Retry(
                total=max_retries,
                connect=max_retries,
                read=max_retries,
                status=max_retries,
                backoff_factor=retry_backoff_seconds,
                status_forcelist=sorted(_RETRYABLE_STATUSES),
                allowed_methods=frozenset({"GET"}),
                raise_on_status=False,
            )
            self._http = urllib3.PoolManager(retries=retry)

    @classmethod
    def from_env(cls) -> "ReferenceDataLookupClient":
        """Build a client from environment variables.

        * ``REFERENCE_DATA_API_BASE_URL`` - base URL of the reference-data API (required for
          lookups to succeed; empty is tolerated at construction but fails on first lookup).
        * ``REFERENCE_DATA_API_TIMEOUT_SECONDS`` - per-request timeout (default ``5``).
        * ``REFERENCE_DATA_API_MAX_RETRIES`` - retry attempts for transient failures (default ``3``).
        * ``REFERENCE_DATA_API_RETRY_BACKOFF_SECONDS`` - backoff factor between retries (default ``0.5``).
        * ``REFERENCE_DATA_API_KEY`` - optional API key sent as the ``X-API-Key`` header.
        """
        return cls(
            os.getenv("REFERENCE_DATA_API_BASE_URL"),
            timeout_seconds=_read_float_env("REFERENCE_DATA_API_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS),
            max_retries=_read_int_env("REFERENCE_DATA_API_MAX_RETRIES", _DEFAULT_MAX_RETRIES),
            retry_backoff_seconds=_read_float_env(
                "REFERENCE_DATA_API_RETRY_BACKOFF_SECONDS", _DEFAULT_RETRY_BACKOFF_SECONDS
            ),
            api_key=os.getenv("REFERENCE_DATA_API_KEY"),
        )

    def lookup(self, dataset: ReferenceDataset, source_code: str) -> str:
        """Resolve ``source_code`` within ``dataset`` to the eMPI target code.

        Raises :class:`ReferenceDataLookupError` if the client is not configured, the source code
        is blank, the API call fails, no mapping exists, or the returned target code is empty or in
        an unexpected format.
        """
        code = (source_code or "").strip()
        if not code:
            # Callers guard against empty/HL7-null source values, so reaching here is a bug.
            raise ReferenceDataLookupError(
                f"Cannot look up an empty source code for dataset '{dataset.path}'."
            )

        if not self._base_url:
            raise ReferenceDataLookupError(
                "Reference-data API is not configured (REFERENCE_DATA_API_BASE_URL is unset); "
                f"cannot resolve '{code}' for dataset '{dataset.path}'."
            )

        url = f"{self._base_url}/lookup/{dataset.path}/{quote(code, safe='')}"
        target_code = self._request_target_code(dataset, code, url)

        if not dataset.pattern.match(target_code):
            raise ReferenceDataLookupError(
                f"Reference-data API returned target code '{target_code}' for dataset "
                f"'{dataset.path}' (source '{code}') in an unexpected format."
            )

        return target_code

    def _request_target_code(self, dataset: ReferenceDataset, code: str, url: str) -> str:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        try:
            response = self._http.request("GET", url, headers=headers, timeout=self._timeout)
        except urllib3.exceptions.HTTPError as exc:
            # Network error / retries exhausted.
            raise ReferenceDataLookupError(
                f"Reference-data API request failed for dataset '{dataset.path}' "
                f"(source '{code}'): {exc}"
            ) from exc

        if response.status == 404:
            raise ReferenceDataLookupError(
                f"No reference-data mapping found for dataset '{dataset.path}' (source '{code}')."
            )

        if response.status != 200:
            raise ReferenceDataLookupError(
                f"Reference-data API returned HTTP {response.status} for dataset "
                f"'{dataset.path}' (source '{code}')."
            )

        try:
            payload = json.loads(response.data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ReferenceDataLookupError(
                f"Reference-data API returned an unparseable body for dataset "
                f"'{dataset.path}' (source '{code}'): {exc}"
            ) from exc

        target_code = payload.get("targetCode") if isinstance(payload, dict) else None
        if not isinstance(target_code, str) or not target_code.strip():
            raise ReferenceDataLookupError(
                f"Reference-data API returned no target code for dataset "
                f"'{dataset.path}' (source '{code}')."
            )

        return target_code.strip()


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer; got '{raw}'.") from exc


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number; got '{raw}'.") from exc
