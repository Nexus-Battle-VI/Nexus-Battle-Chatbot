"""Versión persistida del modelo. El artefacto lo interpreta el adaptador."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from chatbot.domain.training_set import ValidationMetrics


@dataclass(frozen=True)
class ModelVersion:
    id: str
    state: str
    accuracy: float
    macro_f1: float
    metrics: ValidationMetrics
    single_example_labels: tuple[str, ...]
    artifact: bytes
    created_at: datetime
    in_experiment: bool = False


class ModelVersionRepository(Protocol):
    async def active(self) -> ModelVersion | None: ...

    async def add_candidate(self, version: ModelVersion) -> None: ...

    async def promote(self, version_id: str) -> bool: ...

    async def try_acquire(self, now: datetime, until: datetime) -> bool: ...

    async def release(self) -> None: ...

    async def experiment_candidate(self) -> ModelVersion | None: ...

    async def mark_experiment(self, version_id: str) -> bool: ...

    async def list_versions(self) -> tuple[ModelVersion, ...]: ...

    async def record_answer(self, version_id: str, useful: bool | None = None) -> None: ...

    async def rating_counts(self) -> dict[str, tuple[int, int]]: ...
