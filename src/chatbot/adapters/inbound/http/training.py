"""Disparo manual del reentrenamiento (HU-54.4). Exige ADMINISTRATOR.

El cuerpo no existe: la identidad sale del token.
"""

from fastapi import APIRouter, Depends

from chatbot.adapters.inbound.http.auth.guards import require_roles
from chatbot.application.ports.token_verifier import Role
from chatbot.application.train_model import RetrainModel, TrainOutcome

_ADMIN = [Depends(require_roles(Role.ADMINISTRATOR))]


def _view(outcome: TrainOutcome) -> dict[str, object]:
    return {
        "started": outcome.started,
        "promoted": outcome.promoted,
        "versionId": outcome.version_id,
        "accuracy": outcome.accuracy,
        "macroF1": outcome.macro_f1,
        "singleExampleLabels": list(outcome.single_example_labels),
    }


def training_router(retrain: RetrainModel) -> APIRouter:
    router = APIRouter(prefix="/admin/model-training", tags=["model-training"])

    @router.post("", dependencies=_ADMIN)
    async def train() -> dict[str, object]:
        return _view(await retrain.execute())

    return router
