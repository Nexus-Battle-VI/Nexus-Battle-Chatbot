import pytest

from chatbot.infrastructure.config.env import (
    AuthMode,
    CognitoConfig,
    ConfigurationError,
    PersistenceDriver,
    load_config,
)

JWT = {"AUTH_MODE": "jwt", "COGNITO_USER_POOL_ID": "us-east-1_p", "COGNITO_CLIENT_ID": "c"}
POSTGRES = {"PERSISTENCE_DRIVER": "postgres", "DATABASE_URL": "postgresql://db/chatbot"}


def test_valores_por_defecto_de_desarrollo() -> None:
    config = load_config({})
    assert config.app_env == "development"
    assert config.service_name == "nexus-battle-chatbot"
    assert config.port == 3011
    assert config.global_prefix == "api"
    assert config.swagger_enabled is True
    assert config.persistence_driver is PersistenceDriver.MEMORY
    assert config.auth_mode is AuthMode.DISABLED
    assert config.cognito is None
    assert config.database_url is None
    assert config.internal_service_auth_secret is None


def test_configuracion_de_produccion_completa() -> None:
    config = load_config(
        {"APP_ENV": "production", **JWT, **POSTGRES, "INTERNAL_SERVICE_AUTH_SECRET": "s"}
    )
    assert config.cognito == CognitoConfig("us-east-1_p", "c")
    assert config.database_url == "postgresql://db/chatbot"
    assert config.internal_service_auth_secret == "s"
    # La documentacion interactiva no se expone en produccion salvo decision explicita.
    assert config.swagger_enabled is False


def test_produccion_no_arranca_sin_verificacion_de_identidad() -> None:
    with pytest.raises(ConfigurationError, match="AUTH_MODE"):
        load_config({"APP_ENV": "production", **POSTGRES})


def test_produccion_no_arranca_con_persistencia_en_memoria() -> None:
    # Control de la anterior: con identidad configurada, lo que falla es la persistencia.
    with pytest.raises(ConfigurationError, match="PERSISTENCE_DRIVER"):
        load_config({"APP_ENV": "production", **JWT})


def test_postgres_exige_database_url() -> None:
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        load_config({"PERSISTENCE_DRIVER": "postgres"})


def test_jwt_exige_pool_y_cliente() -> None:
    with pytest.raises(ConfigurationError, match="COGNITO"):
        load_config({"AUTH_MODE": "jwt", "COGNITO_USER_POOL_ID": "p"})


@pytest.mark.parametrize(
    ("env", "variable"),
    [
        ({"APP_ENV": "staging"}, "APP_ENV"),
        ({"AUTH_MODE": "abierto"}, "AUTH_MODE"),
        ({"PORT": "tres"}, "PORT"),
        ({"PORT": "70000"}, "PORT"),
        ({"SWAGGER_ENABLED": "si"}, "SWAGGER_ENABLED"),
        ({"LOG_LEVEL": "trace"}, "LOG_LEVEL"),
    ],
)
def test_rechaza_valores_invalidos_nombrando_la_variable(
    env: dict[str, str], variable: str
) -> None:
    with pytest.raises(ConfigurationError, match=variable):
        load_config(env)


def test_cadena_vacia_equivale_a_ausente() -> None:
    assert load_config({"PORT": "", "SWAGGER_ENABLED": "", "SERVICE_NAME": ""}).port == 3011
