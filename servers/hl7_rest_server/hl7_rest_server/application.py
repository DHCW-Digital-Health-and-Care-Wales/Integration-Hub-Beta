from __future__ import annotations

import logging
import os

import uvicorn
from otel_lib import configure_otel

from hl7_rest_server.app import create_app
from hl7_rest_server.app_config import AppConfig
from hl7_rest_server.runtime import build_runtime_context

# Configure application logging.
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Configure Azure SDK logging.
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)


def main() -> None:
    configure_otel("hl7-rest-server")

    config = AppConfig.read_env_config()
    context = build_runtime_context(config)
    app = create_app(context)

    logger.info("HL7 REST server listening on %s:%s", config.host, config.port)
    try:
        uvicorn.run(app, host=config.host, port=config.port, log_level=log_level_str.lower())
    finally:
        context.close()
        logger.info("Server shutdown complete.")


if __name__ == "__main__":
    main()
