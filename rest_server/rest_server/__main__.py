"""Entry point - allows ``python -m rest_server`` execution."""
from __future__ import annotations

import os

import uvicorn

from rest_server.app_config import AppConfig

if __name__ == "__main__":
    config = AppConfig.read_env_config()
    uvicorn.run(
        "rest_server.application:app",
        host=config.host,
        port=config.port,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        ssl_certfile=config.tls_cert_file,
        ssl_keyfile=config.tls_key_file,
    )
