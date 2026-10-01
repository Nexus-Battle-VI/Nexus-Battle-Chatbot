"""Punto de entrada del servicio (`python -m chatbot.main`)."""

import os
import sys

import uvicorn

from chatbot.infrastructure.bootstrap.app import create_app
from chatbot.infrastructure.config.env import ConfigurationError, PersistenceDriver, load_config
from chatbot.infrastructure.observability.logger import JsonLogger
from chatbot.infrastructure.persistence.database import create_pool


def main() -> None:
    try:
        config = load_config(os.environ)
    except ConfigurationError as error:
        # El registro aun no existe si lo que fallo fue la configuracion. La CI
        # comprueba que este mensaje nombra la variable que falta.
        print(f"ConfigurationError: {error}", file=sys.stderr)
        sys.exit(1)

    logger = JsonLogger(level=config.log_level, service=config.service_name, version=config.version)
    pool = (
        create_pool(config.database_url)
        if config.persistence_driver is PersistenceDriver.POSTGRES and config.database_url
        else None
    )
    app = create_app(config, logger=logger, pool=pool)

    logger.info(
        "service_started",
        {
            "port": config.port,
            "globalPrefix": config.global_prefix,
            "persistenceDriver": config.persistence_driver.value,
            "authMode": config.auth_mode.value,
            "swagger": config.swagger_enabled,
        },
    )
    uvicorn.run(
        app,
        # Escucha en todas las interfaces DENTRO del contenedor: Caddy llega por
        # la red de compose. El puerto no se publica en el nodo.
        host="0.0.0.0",  # noqa: S104
        port=config.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
