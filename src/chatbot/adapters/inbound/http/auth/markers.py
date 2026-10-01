"""Marcadores de ruta: equivalen a `@Public()` e `@InternalOnly()` de NestJS.

La proteccion es el comportamiento por defecto: el guard se registra de forma
GLOBAL y hay que EXCLUIR explicitamente lo que deba ser publico. Al reves
-proteger ruta por ruta- cualquier endpoint nuevo naceria desprotegido, y ese
olvido no fallaria ninguna prueba.

Uso (el marcador va DEBAJO del decorador de FastAPI, pegado a la funcion):

    @router.get("/health/live")
    @public
    async def live() -> ...: ...
"""

from collections.abc import Callable
from typing import Any

_PUBLIC = "__nexus_public__"
_INTERNAL = "__nexus_internal__"
_INTERNAL_CALLERS = "__nexus_internal_callers__"

Endpoint = Callable[..., Any]


def public[F: Endpoint](endpoint: F) -> F:
    """Marca una ruta como accesible sin testimonio."""
    setattr(endpoint, _PUBLIC, True)
    return endpoint


def internal_only[F: Endpoint](*callers: str) -> Callable[[F], F]:
    """Exige la firma HMAC del contrato interno.

    Sin argumentos admite a cualquier servicio de `INTERNAL_CALLERS`; con ellos,
    acota la ruta a ese subconjunto. Nunca la amplia: un servicio que no este en
    la lista global se rechaza aunque la ruta lo nombre.
    """

    def mark(endpoint: F) -> F:
        setattr(endpoint, _INTERNAL, True)
        if callers:
            setattr(endpoint, _INTERNAL_CALLERS, tuple(callers))
        return endpoint

    return mark


def is_public(endpoint: object) -> bool:
    return getattr(endpoint, _PUBLIC, False) is True


def is_internal(endpoint: object) -> bool:
    return getattr(endpoint, _INTERNAL, False) is True


def internal_callers_of(endpoint: object) -> tuple[str, ...] | None:
    callers = getattr(endpoint, _INTERNAL_CALLERS, None)
    return callers if isinstance(callers, tuple) else None
