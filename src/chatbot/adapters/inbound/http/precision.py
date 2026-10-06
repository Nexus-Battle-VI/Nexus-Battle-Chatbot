"""Consulta de la precisión en vivo (HU-54.3). Exige ADMINISTRATOR."""

from fastapi import APIRouter, Depends

from chatbot.adapters.inbound.http.auth.guards import require_roles
from chatbot.application.ports.token_verifier import Role
from chatbot.application.precision import ReadModelPrecision, VersionPrecision

_ADMIN = [Depends(require_roles(Role.ADMINISTRATOR))]


def _view(row: VersionPrecision) -> dict[str, object]:
    return {
        "versionId": row.version_id,
        "state": row.state,
        "inExperiment": row.in_experiment,
        "useful": row.useful,
        "notUseful": row.not_useful,
        "precision": row.precision,
    }


def precision_router(reader: ReadModelPrecision) -> APIRouter:
    router = APIRouter(prefix="/admin/model-precision", tags=["model-precision"])

    @router.get("", dependencies=_ADMIN)
    async def read_precision() -> list[dict[str, object]]:
        return [_view(row) for row in await reader.execute()]

    return router
