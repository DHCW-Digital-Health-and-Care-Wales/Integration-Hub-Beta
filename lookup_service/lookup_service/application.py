from __future__ import annotations

import logging
import os

import uvicorn

from lookup_service.app import create_app
from lookup_service.config import Settings

logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # The Azure SDK's HTTP logging includes request URLs, and Cosmos row URLs contain lookup keys.
    azure_level = (os.getenv("AZURE_LOG_LEVEL") or "WARNING").upper()
    logging.getLogger("azure").setLevel(getattr(logging, azure_level, logging.WARNING))
    app = create_app(settings)

    logger.info("Lookup service listening on %s:%s (environment %s)", settings.host, settings.port,
                settings.environment)
    # Access logs are off: lookup keys travel in the query string and must not be logged.
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower(), access_log=False)


if __name__ == "__main__":
    main()
