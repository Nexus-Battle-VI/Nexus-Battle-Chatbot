"""Carga la semilla publicada. Paso explicito, igual que las migraciones.

Se ejecuta con `python -m chatbot.infrastructure.persistence.seed`.
No corre al arrancar el servicio.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from chatbot.adapters.outbound.persistence.postgres_knowledge import (
    PostgresKnowledgeEntryRepository,
)
from chatbot.application.knowledge import ImportKnowledgeEntries, rows_from_document
from chatbot.infrastructure.config.env import load_config
from chatbot.infrastructure.observability.describe_error import describe_error
from chatbot.infrastructure.observability.logger import JsonLogger


def published_seed_path() -> Path:
    override = os.environ.get("CHATBOT_SEED_PATH", "")
    if override != "":
        return Path(override)
    packaged = Path("/app/docs/diccionario/semilla-v1.json")
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[4] / "docs" / "diccionario" / "semilla-v1.json"


async def main() -> int:
    config = load_config(os.environ)
    logger = JsonLogger(level=config.log_level, service=config.service_name, version=config.version)
    if config.database_url is None:
        raise RuntimeError("DATABASE_URL es obligatorio para cargar la semilla.")
    document = json.loads(published_seed_path().read_text(encoding="utf-8"))
    rows = rows_from_document(document)
    pool = AsyncConnectionPool(config.database_url, min_size=0, max_size=1, open=False)
    await pool.open(wait=True)
    try:
        created, skipped = await ImportKnowledgeEntries(
            PostgresKnowledgeEntryRepository(pool)
        ).execute(rows)
    finally:
        await pool.close()
    logger.info("seed_loaded", {"created": created, "skipped": skipped})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as error:
        print(describe_error(error), file=sys.stderr)
        sys.exit(1)
