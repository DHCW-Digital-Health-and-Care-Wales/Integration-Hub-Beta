from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    host : str
    port : int
    hl7_version: str

    @staticmethod
    def read_env_config() -> AppConfig:

        return AppConfig(
            host=_read_required_env("HOST"),
            port= _read_int_required_env("PORT"),
            hl7_version=_read_required_env("HL7_VERSION")
        )


def _read_env(name: str) -> str | None:
    return os.getenv(name)

def _read_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    else:
        return value

def _read_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    return int(value)

def _read_int_required_env(name: str) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    else:
        return int(value)
