"""Configuracion del servicio a partir del entorno.

Equivale a `env.ts` de los servicios NestJS. Es una funcion pura sobre `env`:
no lee `os.environ` directamente, asi que se verifica por completo sin
contaminar el proceso de pruebas.

Falla de inmediato ante una configuracion invalida. Un servicio mal configurado
no debe arrancar y aparentar salud.

`APP_ENV` cumple el papel de `NODE_ENV` en los servicios NestJS.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class ConfigurationError(Exception):
    pass


class AuthMode(StrEnum):
    # Sin verificacion de identidad. Solo para desarrollo y pruebas: un binario
    # con `APP_ENV=production` y este modo NO ARRANCA (ADR-004).
    DISABLED = "disabled"
    # Se exige un testimonio firmado por el user pool de Cognito.
    JWT = "jwt"


class PersistenceDriver(StrEnum):
    MEMORY = "memory"
    POSTGRES = "postgres"


@dataclass(frozen=True)
class CognitoConfig:
    user_pool_id: str
    client_id: str


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    service_name: str
    version: str
    log_level: str
    port: int
    global_prefix: str
    swagger_enabled: bool
    persistence_driver: PersistenceDriver
    database_url: str | None
    auth_mode: AuthMode
    cognito: CognitoConfig | None
    internal_service_auth_secret: str | None


RawEnv = Mapping[str, str | None]


def _read_string(env: RawEnv, key: str, fallback: str) -> str:
    raw = env.get(key)
    return fallback if raw is None or raw == "" else raw


def _read_enum(env: RawEnv, key: str, allowed: tuple[str, ...], fallback: str) -> str:
    raw = env.get(key)
    if raw is None or raw == "":
        return fallback
    if raw not in allowed:
        raise ConfigurationError(
            f'{key} debe ser uno de: {", ".join(allowed)}. Se recibio "{raw}".'
        )
    return raw


def _read_integer(env: RawEnv, key: str, fallback: int, minimum: int, maximum: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return fallback
    try:
        parsed = int(raw, 10)
    except ValueError:
        raise ConfigurationError(f'{key} debe ser un numero entero. Se recibio "{raw}".') from None
    if parsed < minimum or parsed > maximum:
        raise ConfigurationError(
            f"{key} debe estar entre {minimum} y {maximum}. Se recibio {parsed}."
        )
    return parsed


def _read_boolean(env: RawEnv, key: str, fallback: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw == "":
        return fallback
    if raw not in ("true", "false"):
        raise ConfigurationError(f'{key} debe ser "true" o "false". Se recibio "{raw}".')
    return raw == "true"


def load_config(env: RawEnv) -> AppConfig:
    app_env = _read_enum(env, "APP_ENV", ("development", "test", "production"), "development")

    persistence_driver = PersistenceDriver(
        _read_enum(
            env,
            "PERSISTENCE_DRIVER",
            tuple(PersistenceDriver),
            PersistenceDriver.MEMORY,
        )
    )
    database_url = _read_string(env, "DATABASE_URL", "")
    if persistence_driver is PersistenceDriver.POSTGRES and database_url == "":
        raise ConfigurationError(
            'DATABASE_URL es obligatorio cuando PERSISTENCE_DRIVER es "postgres".'
        )

    auth_mode = AuthMode(_read_enum(env, "AUTH_MODE", tuple(AuthMode), AuthMode.DISABLED))
    if app_env == "production" and auth_mode is AuthMode.DISABLED:
        raise ConfigurationError(
            'AUTH_MODE no puede ser "disabled" con APP_ENV=production. Sin verificacion de '
            "identidad el servicio no debe exponerse. Vease ADR-004."
        )

    user_pool_id = _read_string(env, "COGNITO_USER_POOL_ID", "")
    client_id = _read_string(env, "COGNITO_CLIENT_ID", "")
    if auth_mode is AuthMode.JWT and (user_pool_id == "" or client_id == ""):
        raise ConfigurationError(
            'COGNITO_USER_POOL_ID y COGNITO_CLIENT_ID son obligatorios cuando AUTH_MODE es "jwt".'
        )

    # Se comprueba DESPUES de la identidad a proposito: la imagen sin configurar
    # debe negarse a arrancar nombrando AUTH_MODE, que es lo que verifica la CI.
    #
    # Una conversacion o un modelo que desaparecen al reiniciar no existen. La
    # persistencia en memoria es un doble de desarrollo, nunca un modo de produccion.
    if app_env == "production" and persistence_driver is PersistenceDriver.MEMORY:
        raise ConfigurationError(
            'PERSISTENCE_DRIVER no puede ser "memory" con APP_ENV=production. Vease ADR-022.'
        )

    secret = _read_string(env, "INTERNAL_SERVICE_AUTH_SECRET", "")

    return AppConfig(
        app_env=app_env,
        service_name=_read_string(env, "SERVICE_NAME", "nexus-battle-chatbot"),
        version=_read_string(env, "SERVICE_VERSION", "0.1.0"),
        log_level=_read_enum(env, "LOG_LEVEL", ("debug", "info", "warn", "error"), "info"),
        port=_read_integer(env, "PORT", 3011, 1, 65_535),
        global_prefix=_read_string(env, "GLOBAL_PREFIX", "api"),
        # La documentacion interactiva permanece deshabilitada en produccion salvo
        # decision explicita: expone la superficie completa de la API.
        swagger_enabled=_read_boolean(env, "SWAGGER_ENABLED", app_env != "production"),
        persistence_driver=persistence_driver,
        database_url=None if database_url == "" else database_url,
        auth_mode=auth_mode,
        cognito=CognitoConfig(user_pool_id, client_id) if auth_mode is AuthMode.JWT else None,
        internal_service_auth_secret=None if secret == "" else secret,
    )
