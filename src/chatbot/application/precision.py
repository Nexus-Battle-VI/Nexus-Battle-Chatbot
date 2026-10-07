"""Precisión en vivo por versión. No es la exactitud de la validación."""

from dataclasses import dataclass

from chatbot.application.ports.model_version_repository import ModelVersionRepository
from chatbot.domain.experiment import live_precision


@dataclass(frozen=True)
class VersionPrecision:
    version_id: str
    state: str
    in_experiment: bool
    accuracy: float
    macro_f1: float
    useful: int
    not_useful: int
    precision: float | None
    per_intent_f1: tuple[tuple[str, float], ...]
    confusion: tuple[tuple[str, str, int], ...]


class ReadModelPrecision:
    def __init__(self, versions: ModelVersionRepository) -> None:
        self._versions = versions

    async def execute(self) -> tuple[VersionPrecision, ...]:
        counts = await self._versions.rating_counts()
        rows: list[VersionPrecision] = []
        for version in await self._versions.list_versions():
            useful, not_useful = counts.get(version.id, (0, 0))
            rows.append(
                VersionPrecision(
                    version.id,
                    version.state,
                    version.in_experiment,
                    version.accuracy,
                    version.macro_f1,
                    useful,
                    not_useful,
                    live_precision(useful, not_useful),
                    version.metrics.per_intent_f1,
                    version.metrics.confusion,
                )
            )
        return tuple(rows)
