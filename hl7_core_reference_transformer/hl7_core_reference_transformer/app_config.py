"""WRDS-specific configuration, read directly from environment variables.

Kept separate from transformer_base_lib's AppConfig/TransformerConfig (Service Bus/health-check
settings) since these are specific to the WRDS SOAP integration used by this transformer only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_TIMEOUT_SECONDS = 30
_DEFAULT_LOOKUP_TABLE_NAME = "FioranoCodeTranslation"


@dataclass
class WRDSConfig:
    endpoint_url: str
    timeout_seconds: int
    client_cert_path: str | None
    lookup_table_name: str
    local_fixture_path: str | None = None

    @staticmethod
    def read_env_config() -> "WRDSConfig":
        endpoint_url = os.getenv("WRDS_ENDPOINT_URL")
        if not endpoint_url:
            raise ValueError("WRDS_ENDPOINT_URL environment variable is required")

        timeout_seconds_str = os.getenv("WRDS_TIMEOUT_SECONDS")
        timeout_seconds = int(timeout_seconds_str) if timeout_seconds_str else _DEFAULT_TIMEOUT_SECONDS

        return WRDSConfig(
            endpoint_url=endpoint_url,
            timeout_seconds=timeout_seconds,
            client_cert_path=os.getenv("WRDS_CLIENT_CERT_PATH") or None,
            lookup_table_name=os.getenv("WRDS_LOOKUP_TABLE_NAME") or _DEFAULT_LOOKUP_TABLE_NAME,
            local_fixture_path=os.getenv("WRDS_LOCAL_FIXTURE_PATH") or None,
        )
