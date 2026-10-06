"""Precisión en vivo por versión. No es la exactitud de la validación."""

from dataclasses import dataclass

from chatbot.application.ports.model_version_repository import ModelVersionRepository
from chatbot.domain.experiment import live_precision


@dataclass(frozen=True)
class VersionPrecision:
    version_id: str
    state: str
    in_experiment: bool
    useful: int
    not_useful: int
    precision: float | None


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
                    useful,
                    not_useful,
                    live_precision(useful, not_useful),
                )
            )
        return tuple(rows)
