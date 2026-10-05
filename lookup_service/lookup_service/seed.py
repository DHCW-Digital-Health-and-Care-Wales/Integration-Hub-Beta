from __future__ import annotations

import logging
from pathlib import Path

from lookup_service.models import UploadInfo
from lookup_service.store.base import TableStore
from lookup_service.store.file_store import SEED_ACTOR, FileTableStore

logger = logging.getLogger(__name__)


async def import_missing_seed_tables(store: TableStore, seed_dir: Path) -> list[str]:
    """Import seed CSVs into a writable store for tables that don't exist there yet.

    Existing tables are never overwritten, so uploads made through the GUI survive restarts and
    redeploys. Seed files are fully validated first; a bad seed file stops startup.
    """
    if not store.writable:
        return []
    if not seed_dir.is_dir():
        logger.warning("Seed directory %s not found; skipping seed import", seed_dir)
        return []

    seeds = FileTableStore.load(seed_dir)
    existing = {record.definition.name for record in await store.list_tables()}
    imported = []
    for table in seeds.loaded_tables:
        name = table.definition.name
        if name in existing:
            continue
        await store.replace_table(table.definition, list(table.rows.values()),
                                  UploadInfo(actor=SEED_ACTOR, file_name=table.source_file))
        imported.append(name)
        logger.info("Seeded table %s with %d row(s) from %s", name, len(table.rows), table.source_file)
    return imported
