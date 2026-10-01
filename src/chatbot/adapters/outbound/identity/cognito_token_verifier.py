"""Verificador de testimonios emitidos por un user pool de Cognito.

Equivale a `CognitoTokenVerifier.ts` (que usa `aws-jwt-verify`). La firma la
comprueba PyJWT contra el JWKS del pool; no se implementa criptografia a mano:
es la clase de codigo donde un error sutil no falla, sino que acepta tokens
falsificados en silencio.

Se verifica el token de ACCESO, no el de identidad: es el que autoriza una
peticion y el unico cuyo `client_id` puede comprobarse contra el cliente
esperado. Se exigen las mismas reclamaciones que `aws-jwt-verify`: firma RS256
del pool, `iss` del pool, `exp` vigente, `token_use=access` y `client_id`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import anyio
import jwt

from chatbot.application.ports.token_verifier import (
    Role,
    TokenVerificationError,
    VerifiedIdentity,
    is_role,
)


@dataclass(frozen=True)
class CognitoTokenVerifierOptions:
    user_pool_id: str
    client_id: str
    region: str | None = None

    @property
    def issuer(self) -> str:
        # El identificador del pool empieza por la region (`us-east-1_...`).
        region = self.region or self.user_pool_id.split("_", 1)[0]
        return f"https://cognito-idp.{region}.amazonaws.com/{self.user_pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"


class SigningKeySource(Protocol):
    """Origen de la clave publica que firmo un token (el JWKS del pool)."""

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


class CognitoTokenVerifier:
    def __init__(
        self,
        options: CognitoTokenVerifierOptions,
        keys: SigningKeySource | None = None,
    ) -> None:
        self._options = options
        # PyJWKClient descarga y cachea el JWKS. Se puede sustituir en pruebas
        # para no depender de red ni de un pool real.
        self._keys: SigningKeySource = keys or jwt.PyJWKClient(
            options.jwks_url, cache_keys=True, lifespan=3600, timeout=5
        )

    async def verify(self, token: str) -> VerifiedIdentity:
        try:
            # La descarga del JWKS es bloqueante: se saca del bucle de eventos.
            payload = await anyio.to_thread.run_sync(self._decode, token)
        except jwt.PyJWTError as error:
            # El motivo exacto no se propaga: distinguir "firma invalida" de
            # "caducado" ayuda a quien esta probando tokens falsificados.
            raise TokenVerificationError() from error

        return to_verified_identity(payload)

    def _decode(self, token: str) -> dict[str, object]:
        signing_key = self._keys.get_signing_key_from_jwt(token)
        payload: dict[str, object] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=self._options.issuer,
            # El token de acceso de Cognito no lleva `aud`; el cliente se
            # comprueba con `client_id`, justo debajo.
            options={"require": ["exp", "iat", "iss", "sub", "token_use"], "verify_aud": False},
        )
        if payload.get("token_use") != "access":
            raise jwt.InvalidTokenError("token_use")
        if payload.get("client_id") != self._options.client_id:
            raise jwt.InvalidTokenError("client_id")
        return payload


def to_verified_identity(payload: Mapping[str, object]) -> VerifiedIdentity:
    """Traduce el contenido del token a la identidad verificada.

    Es pura y se exporta a proposito: decide QUE roles y QUE correo se aceptan, y
    debe poder probarse sin red. La comprobacion de firma queda en la biblioteca.
    """
    subject = payload.get("sub")
    # Un token sin `sub` no identifica a nadie, por muy valida que sea su firma.
    if not isinstance(subject, str) or subject == "":
        raise TokenVerificationError()

    return VerifiedIdentity(
        subject=subject,
        email=_read_verified_email(payload),
        roles=_read_roles(payload),
    )


def _read_verified_email(payload: Mapping[str, object]) -> str | None:
    # Un correo sin verificar es una afirmacion del usuario, no un hecho
    # comprobado: usarlo para decidir permisos permitiria suplantar a cualquiera.
    verified = payload.get("email_verified")
    email = payload.get("email")
    if verified is not True and verified != "true":
        return None
    return email.lower() if isinstance(email, str) and email != "" else None


def _read_roles(payload: Mapping[str, object]) -> frozenset[Role]:
    # Los grupos que no son un rol conocido se descartan en silencio. Aceptarlos
    # convertiria el pool en una fuente de roles arbitrarios.
    groups = payload.get("cognito:groups")
    if not isinstance(groups, list):
        return frozenset()
    return frozenset(Role(group) for group in groups if isinstance(group, str) and is_role(group))
