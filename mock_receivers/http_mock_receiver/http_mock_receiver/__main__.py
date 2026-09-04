"""Entry point — allows ``python -m http_mock_receiver`` execution."""
from __future__ import annotations

import uvicorn

from http_mock_receiver.app_config import AppConfig

if __name__ == "__main__":
    config = AppConfig.read_env_config()
    uvicorn.run(
        "http_mock_receiver.application:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )
