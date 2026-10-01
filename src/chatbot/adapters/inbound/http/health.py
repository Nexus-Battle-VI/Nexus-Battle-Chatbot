"""Sondas de salud del servicio.

Responden sin testimonio: un orquestador no lo tiene, y una sonda que exige
autenticacion reporta el servicio como caido. `ready` responde 503 cuando alguna
dependencia falla, para dejar de recibir trafico en lugar de fingir que esta
disponible.
"""

from collections.abc import Sequence

from fastapi import APIRouter, Request, Response, status

from chatbot.adapters.inbound.http.auth.markers import public
from chatbot.infrastructure.health.health import (
    ReadinessCheck,
    build_liveness,
    build_readiness,
    build_version,
)

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Confirma que el proceso responde")
@public
async def live() -> dict[str, object]:
    return build_liveness()


@router.get(
    "/health/ready",
    summary="Evalua las dependencias del servicio",
    responses={503: {"description": "Alguna dependencia no responde"}},
)
@public
async def ready(request: Request, response: Response) -> dict[str, object]:
    checks: Sequence[ReadinessCheck] = request.app.state.readiness_checks
    report = await build_readiness(checks)
    response.status_code = (
        status.HTTP_200_OK if report["status"] == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return report


@router.get("/version", summary="Expone servicio, version y entorno")
@public
async def version(request: Request) -> dict[str, str]:
    info: dict[str, str] = request.app.state.version_info
    return build_version(info["service"], info["version"], info["environment"])
