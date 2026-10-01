"""Guards globales, equivalentes a los de los servicios NestJS.

Se ejecutan en el MISMO orden que alli (`app.module.ts`): primero la identidad,
despues los roles (por ruta, con `require_roles`), despues el contrato interno,
que solo actua sobre rutas `@internal_only`.
"""

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import NoReturn

from fastapi import HTTPException, Request, status

from chatbot.adapters.inbound.http.auth.markers import (
    internal_callers_of,
    is_internal,
    is_public,
)
from chatbot.adapters.outbound.identity.internal_signature import (
    INTERNAL_CLOCK_SKEW_MS,
    INTERNAL_SERVICE_HEADER,
    INTERNAL_SIGNATURE_HEADER,
    INTERNAL_TIMESTAMP_HEADER,
    CanonicalRequest,
    sign_internal_request,
    signature_matches,
    timestamp_within_window,
)
from chatbot.application.ports.clock import ClockPort
from chatbot.application.ports.token_verifier import (
    ALL_ROLES,
    Role,
    TokenVerificationError,
    TokenVerifierPort,
    VerifiedIdentity,
)
from chatbot.infrastructure.observability.logger import Logger

# Identidad que se atribuye a toda peticion con `AUTH_MODE=disabled`.
#
# El sujeto es la cadena literal `anonymous`: sin proveedor de identidad NO SE
# SABE quien realiza la peticion, y el dato guardado debe decirlo en lugar de
# atribuirlo a una persona que nadie verifico. Se conceden todos los roles
# porque sin identidad no hay forma de distinguirlos. No es una puerta trasera:
# con `APP_ENV=production` y este modo el servicio NO ARRANCA.
ANONYMOUS_IDENTITY = VerifiedIdentity(subject="anonymous", email=None, roles=ALL_ROLES)


@dataclass(frozen=True)
class AuthSettings:
    jwt_enabled: bool
    verifier: TokenVerifierPort
    internal_secret: str | None
    internal_callers: tuple[str, ...]
    clock: ClockPort
    logger: Logger
    skew_ms: int = INTERNAL_CLOCK_SKEW_MS


def _settings(request: Request) -> AuthSettings:
    settings: AuthSettings = request.app.state.auth
    return settings


def _endpoint(request: Request) -> object:
    route = request.scope.get("route")
    return getattr(route, "endpoint", None)


def read_bearer_token(header: str | None) -> str | None:
    """Exactamente `Bearer <token>`.

    Con un `split` laxo, `Bearer token sobra` pasaria leyendo solo el segundo
    campo: se aceptaria una cabecera que ningun cliente correcto envia.
    """
    if header is None:
        return None
    parts = header.split(" ")
    if len(parts) != 2:
        return None
    scheme, value = parts
    if scheme.lower() != "bearer" or value == "":
        return None
    return value


async def authenticate(request: Request) -> None:
    """Dependencia GLOBAL: identidad y, si la ruta es interna, firma HMAC."""
    settings = _settings(request)
    endpoint = _endpoint(request)
    internal = is_internal(endpoint)

    if not settings.jwt_enabled:
        request.state.identity = ANONYMOUS_IDENTITY
    elif not (is_public(endpoint) or internal):
        token = read_bearer_token(request.headers.get("authorization"))
        if token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el testimonio de identidad.")
        try:
            request.state.identity = await settings.verifier.verify(token)
        except TokenVerificationError as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
        # Un fallo que no es de verificacion (red, JWKS inalcanzable) no se
        # traduce a 401: diria que el testimonio es invalido cuando lo que ocurre
        # es que no se pudo comprobar. Se propaga como 500.

    if internal:
        await _verify_internal(request, settings, internal_callers_of(endpoint))


async def _verify_internal(
    request: Request, settings: AuthSettings, route_callers: Sequence[str] | None
) -> None:
    # SIN SECRETO CONFIGURADO, NIEGA con 503. Dejar pasar ante una configuracion
    # incompleta convertiria un despliegue a medias en un endpoint interno abierto.
    if not settings.internal_secret:
        settings.logger.error(
            "internal_auth_sin_secreto",
            {
                "detail": "INTERNAL_SERVICE_AUTH_SECRET no esta configurado: "
                "el contrato interno niega."
            },
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "El contrato interno no esta disponible."
        )

    service = request.headers.get(INTERNAL_SERVICE_HEADER)
    timestamp = request.headers.get(INTERNAL_TIMESTAMP_HEADER)
    signature = request.headers.get(INTERNAL_SIGNATURE_HEADER)
    # NO REVELA POR QUE FALLA: el motivo se registra, la respuesta es siempre la misma.
    if service is None or timestamp is None or signature is None:
        _reject(settings, "cabeceras_incompletas")
    # Con la cabecera repetida, Starlette devuelve la primera, como NestJS.
    if service not in settings.internal_callers:
        _reject(settings, "servicio_no_permitido")
    if route_callers is not None and service not in route_callers:
        _reject(settings, "servicio_no_autorizado_para_ruta")
    if not timestamp_within_window(timestamp, settings.clock.now(), settings.skew_ms):
        _reject(settings, "sello_fuera_de_ventana")

    raw = await request.body()
    try:
        body: object = json.loads(raw) if raw else {}
    except ValueError:
        _reject(settings, "cuerpo_no_json")

    expected = sign_internal_request(
        settings.internal_secret,
        CanonicalRequest(
            service=service,
            method=request.method,
            # Sin la cadena de consulta: es la misma ruta que firma quien llama.
            path=request.url.path,
            timestamp=timestamp,
            body=body,
        ),
    )
    if not signature_matches(expected, signature):
        _reject(settings, "firma_invalida")
    # `caller` y no `service`: esa clave ya identifica a ESTE servicio en el registro.
    settings.logger.info("internal_auth_aceptada", {"caller": service})


def _reject(settings: AuthSettings, reason: str) -> NoReturn:
    settings.logger.warn("internal_auth_rechazada", {"reason": reason})
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Peticion interna no autorizada.")


def _satisfies(held: frozenset[Role], required: Role) -> bool:
    """El super administrador satisface toda exigencia de administrador.

    Se resuelve AQUI y no anadiendo el rol a cada ruta: olvidarlo en una nueva
    produce un 403 mudo. La relacion es de UN SOLO SENTIDO.
    """
    if required in held:
        return True
    return required is Role.ADMINISTRATOR and Role.SUPER_ADMINISTRATOR in held


def require_roles(*roles: Role) -> Callable[[Request], Awaitable[None]]:
    """Exige que la identidad verificada tenga al menos uno de los roles."""

    async def check(request: Request) -> None:
        if not roles:
            return
        identity: VerifiedIdentity | None = getattr(request.state, "identity", None)
        if identity is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "La peticion no lleva una identidad verificada."
            )
        if not any(_satisfies(identity.roles, role) for role in roles):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "La identidad no posee el rol necesario para esta operacion.",
            )

    return check


def current_identity(request: Request) -> VerifiedIdentity:
    """Identidad ya verificada. Nunca lee nada del cuerpo ni de la URL.

    Falla cerrado con 401 si no hay identidad, en vez de un error opaco.
    """
    identity: VerifiedIdentity | None = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "La peticion no llego con una identidad verificada."
        )
    return identity
