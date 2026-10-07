"""Versiones del modelo en memoria. El proceso las pierde al reiniciar."""

from datetime import UTC, datetime

from chatbot.application.ports.model_version_repository import ModelVersion


class InMemoryModelVersionRepository:
    def __init__(self) -> None:
        self._versions: list[ModelVersion] = []
        self._until = datetime.min.replace(tzinfo=UTC)
        self._ratings: list[tuple[str, bool | None]] = []

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
                demoted.append(_with_state(version, "CANDIDATE", False))
            elif version.id == version_id and version.state == "CANDIDATE":
                demoted.append(_with_state(version, "ACTIVE", False))
                found = True
            else:
                demoted.append(_with_state(version, version.state, version.in_experiment))
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

    async def experiment_candidate(self) -> ModelVersion | None:
        for version in self._versions:
            if version.state == "CANDIDATE" and version.in_experiment:
                return version
        return None

    async def mark_experiment(self, version_id: str) -> bool:
        found = False
        marked: list[ModelVersion] = []
        for version in self._versions:
            chosen = version.id == version_id and version.state == "CANDIDATE"
            marked.append(_with_state(version, version.state, chosen))
            found = found or chosen
        if found:
            self._versions = marked
        return found

    async def list_versions(self) -> tuple[ModelVersion, ...]:
        return tuple(self._versions)

    async def record_answer(self, version_id: str, useful: bool | None = None) -> None:
        self._ratings.append((version_id, useful))

    async def rating_counts(self) -> dict[str, tuple[int, int]]:
        counts: dict[str, tuple[int, int]] = {}
        for version_id, useful in self._ratings:
            useful_count, not_useful = counts.get(version_id, (0, 0))
            if useful is True:
                useful_count += 1
            elif useful is False:
                not_useful += 1
            counts[version_id] = (useful_count, not_useful)
        return counts


def _with_state(version: ModelVersion, state: str, in_experiment: bool) -> ModelVersion:
    return ModelVersion(
        id=version.id,
        state=state,
        accuracy=version.accuracy,
        macro_f1=version.macro_f1,
        metrics=version.metrics,
        single_example_labels=version.single_example_labels,
        artifact=version.artifact,
        created_at=version.created_at,
        in_experiment=in_experiment,
    )
