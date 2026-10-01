"""Sondas de salud: liveness, readiness y version."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    # Es asincrona: comprobar una base de datos exige ir hasta ella. Una sonda
    # que solo mira si existe el objeto que la representa no dice nada.
    check: Callable[[], Awaitable[bool]]


def build_liveness() -> dict[str, object]:
    """El proceso responde. No consulta dependencias: reiniciar el servicio no
    repara una dependencia caida."""
    return {"status": "ok", "checks": {}}


async def build_readiness(checks: Sequence[ReadinessCheck]) -> dict[str, object]:
    """Evalua las dependencias reales.

    Una comprobacion que lanza cuenta como fallo, nunca como exito: una
    readiness falsa es peor que no tenerla.
    """

    async def run(item: ReadinessCheck) -> tuple[str, str]:
        try:
            outcome = "ok" if await item.check() else "error"
        except Exception:
            outcome = "error"
        return item.name, outcome

    results = dict(await asyncio.gather(*(run(item) for item in checks)))
    healthy = all(outcome == "ok" for outcome in results.values())
    return {"status": "ok" if healthy else "error", "checks": results}


def build_version(service: str, version: str, environment: str) -> dict[str, str]:
    return {"service": service, "version": version, "environment": environment}
