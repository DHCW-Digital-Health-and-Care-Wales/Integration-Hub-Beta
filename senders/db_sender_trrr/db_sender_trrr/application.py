from __future__ import annotations

import json
import logging
from typing import Any

from .app_config import AppConfig
from .db_client import DatabaseClient
from .identifier_mapper import map_adt_a05_identifiers

logger = logging.getLogger(__name__)


def process_message(message: str, *, client: DatabaseClient | None = None) -> dict[str, Any]:
    """Validate and persist a TRRR identifier association for ADT_A05 messages."""
    payload = map_adt_a05_identifiers(message)
    if client is None:
        raise ValueError("DatabaseClient is required before sending a TRRR update")

    request = {
        "type": "TRRR_IDENTIFIER_ASSOCIATION",
        **payload,
    }
    logger.info("Creating database update request for LIMS=%s NHS=%s", payload["LIMSIdentifier"], payload["NewIdentifier"])
    return client.execute_stored_procedure(json.dumps(request, ensure_ascii=False), is_priority=False)


def main() -> None:
    config = AppConfig.read_env_config()
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    client = DatabaseClient.from_config(config)

    sample_message = (
        "MSH|^~\\&|TEST|WLIMS|MPI|HIS|20250101120000||ADT^A05|MSG|P|2.5\r"
        "PID|1||12345^^^328^PI||SMITH^JOHN||19800101|M|||||||9876543210^^^NHS^NH\r"
    )

    processed = process_message(sample_message, client=client)
    logger.info("Processed TRRR request: %s", json.dumps(processed, ensure_ascii=False))


if __name__ == "__main__":
    main()
