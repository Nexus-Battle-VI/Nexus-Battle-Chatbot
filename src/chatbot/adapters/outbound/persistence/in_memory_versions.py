"""Versiones del modelo en memoria. El proceso las pierde al reiniciar."""

from datetime import UTC, datetime

from chatbot.application.ports.model_version_repository import ModelVersion


class InMemoryModelVersionRepository:
    def __init__(self) -> None:
        self._versions: list[ModelVersion] = []
        self._until = datetime.min.replace(tzinfo=UTC)

    async def active(self) -> ModelVersion | None:
        for version in self._versions:
            if version.state == "ACTIVE":
                return version
        return None

    async def add_candidate(self, version: ModelVersion) -> None:
        self._versions.append(version)

    async def promote(self, version_id: str) -> bool:
        found = False
        demoted: list[ModelVersion] = []
        for version in self._versions:
            if version.state == "ACTIVE":
                demoted.append(_with_state(version, "CANDIDATE"))
            elif version.id == version_id and version.state == "CANDIDATE":
                demoted.append(_with_state(version, "ACTIVE"))
                found = True
            else:
                demoted.append(version)
        if found:
            self._versions = demoted
        return found

    async def try_acquire(self, now: datetime, until: datetime) -> bool:
        if self._until > now:
            return False
        self._until = until
        return True

    async def release(self) -> None:
        self._until = datetime.min.replace(tzinfo=UTC)


def _with_state(version: ModelVersion, state: str) -> ModelVersion:
    return ModelVersion(
        id=version.id,
        state=state,
        accuracy=version.accuracy,
        macro_f1=version.macro_f1,
        metrics=version.metrics,
        single_example_labels=version.single_example_labels,
        artifact=version.artifact,
        created_at=version.created_at,
    )
