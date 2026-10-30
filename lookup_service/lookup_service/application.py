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
    # Behind the Container Apps ingress (which terminates TLS) the browser's scheme only arrives in
    # X-Forwarded-Proto. Uvicorn ignores it unless the peer is trusted, so generated URLs became http:// and
    # the browser blocked the CSS/JS as mixed content. The ingress is internal-only and the sole way in, so
    # trust it by default; FORWARDED_ALLOW_IPS narrows this.
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS") or "*",
    )


if __name__ == "__main__":
    main()
