"""Verificador de Cognito sin red: tokens firmados con una clave RSA de prueba.

Cada rechazo cambia UNA sola condicion del token valido, que es su control: si el
token base no pasara, todos los rechazos serian ciertos por construccion.
"""

import time
from collections.abc import Mapping

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from chatbot.adapters.outbound.identity.cognito_token_verifier import (
    CognitoTokenVerifier,
    CognitoTokenVerifierOptions,
    to_verified_identity,
)
from chatbot.application.ports.token_verifier import Role, TokenVerificationError

OPTIONS = CognitoTokenVerifierOptions(user_pool_id="us-east-1_Pruebas", client_id="cliente")
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FixedKeys:
    """Sustituye al JWKS del pool: siempre devuelve la clave publica de KEY."""

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        return jwt.PyJWK.from_dict(
            {**jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "alg": "RS256"}
        )


def _token(overrides: Mapping[str, object] | None = None, *, key: object = KEY) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "sujeto-1",
        "iss": OPTIONS.issuer,
        "token_use": "access",
        "client_id": "cliente",
        "iat": now,
        "exp": now + 300,
        "cognito:groups": ["PLAYER", "INVENTADO"],
    }
    claims.update(overrides or {})
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256")  # type: ignore[arg-type]


@pytest.fixture
def verifier() -> CognitoTokenVerifier:
    return CognitoTokenVerifier(OPTIONS, keys=FixedKeys())


@pytest.mark.anyio
async def test_acepta_un_token_de_acceso_valido(verifier: CognitoTokenVerifier) -> None:
    identity = await verifier.verify(_token())
    assert identity.subject == "sujeto-1"
    # El grupo inventado se descarta: un grupo del pool no fabrica un permiso.
    assert identity.roles == frozenset({Role.PLAYER})


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("caso", "overrides", "key"),
    [
        ("firma de otra clave", {}, OTHER_KEY),
        ("token de identidad, no de acceso", {"token_use": "id"}, KEY),
        ("otro cliente", {"client_id": "otro"}, KEY),
        ("otro emisor", {"iss": "https://cognito-idp.us-east-1.amazonaws.com/otro"}, KEY),
        ("caducado", {"exp": int(time.time()) - 10}, KEY),
        ("sin token_use", {"token_use": None}, KEY),
    ],
)
async def test_rechaza(
    verifier: CognitoTokenVerifier, caso: str, overrides: dict[str, object], key: object
) -> None:
    with pytest.raises(TokenVerificationError):
        await verifier.verify(_token(overrides, key=key))


@pytest.mark.anyio
async def test_rechaza_un_token_mal_formado(verifier: CognitoTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        await verifier.verify("no-es-un-jwt")


def test_construye_emisor_y_jwks_del_pool() -> None:
    assert OPTIONS.issuer == "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Pruebas"
    assert OPTIONS.jwks_url.endswith("/us-east-1_Pruebas/.well-known/jwks.json")
    # Sin `keys`, usa el cliente JWKS real (no se invoca: no hay red en pruebas).
    assert CognitoTokenVerifier(OPTIONS) is not None


def test_un_token_sin_sub_no_identifica_a_nadie() -> None:
    with pytest.raises(TokenVerificationError):
        to_verified_identity({"sub": ""})
    with pytest.raises(TokenVerificationError):
        to_verified_identity({})


def test_solo_acepta_el_correo_verificado() -> None:
    assert to_verified_identity({"sub": "s", "email": "A@B.CO", "email_verified": True}).email == (
        "a@b.co"
    )
    assert to_verified_identity({"sub": "s", "email": "a@b.co", "email_verified": "true"}).email
    assert to_verified_identity({"sub": "s", "email": "a@b.co", "email_verified": False}).email is (
        None
    )
    assert to_verified_identity({"sub": "s", "email": "", "email_verified": True}).email is None


def test_reconoce_al_super_administrador_y_descarta_lo_que_no_es_rol() -> None:
    identity = to_verified_identity(
        {"sub": "s", "cognito:groups": ["SUPER_ADMINISTRATOR", 7, "ADMIN"]}
    )
    assert identity.roles == frozenset({Role.SUPER_ADMINISTRATOR})
    assert to_verified_identity({"sub": "s", "cognito:groups": "PLAYER"}).roles == frozenset()
