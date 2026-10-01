"""Punto de entrada del contenedor `chatbot-migrate`.

Se ejecuta con `python -m chatbot.infrastructure.persistence.migrate`.

Es un paso explicito del despliegue y no algo que ocurra al arrancar el
servicio: un despliegue con una migracion rota falla una sola vez, de forma
visible, en lugar de dejar el servicio en bucle de reinicio.
"""

import asyncio
import os
import sys

from psycopg import AsyncConnection

from chatbot.infrastructure.config.env import load_config
from chatbot.infrastructure.observability.describe_error import describe_error
from chatbot.infrastructure.observability.logger import JsonLogger
from chatbot.infrastructure.persistence.database import migrate_to_latest


async def main() -> int:
    config = load_config(os.environ)
    logger = JsonLogger(level=config.log_level, service=config.service_name, version=config.version)
    if config.database_url is None:
        raise RuntimeError("DATABASE_URL es obligatorio para ejecutar las migraciones.")

    connection = await AsyncConnection.connect(config.database_url, connect_timeout=10)
    try:
        outcome = await migrate_to_latest(connection)
    finally:
        await connection.close()

    for name in outcome.applied:
        logger.info("migration_applied", {"migration": name})
    if outcome.error is not None:
        raise RuntimeError(f"La migracion fallo: {describe_error(outcome.error)}")
    logger.info("migrations_up_to_date", {"applied": len(outcome.applied)})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as error:
        # El registro no existe si lo que fallo fue la configuracion: este es el
        # unico sitio donde escribir directamente esta justificado.
        print(describe_error(error), file=sys.stderr)
        sys.exit(1)
