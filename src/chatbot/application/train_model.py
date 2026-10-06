"""Reentrena una candidata y la promueve solo si la validación lo permite (HU-54.2)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from chatbot.application.ports.clock import ClockPort
from chatbot.application.ports.knowledge_entry_repository import KnowledgeEntryRepositoryPort
from chatbot.application.ports.model_trainer import ModelTrainer
from chatbot.application.ports.model_version_repository import (
    ModelVersion,
    ModelVersionRepository,
)
from chatbot.application.ports.reviewed_conversations import ReviewedConversationPort
from chatbot.domain.training_set import (
    conversation_example,
    dictionary_examples,
    should_promote,
    split_examples,
    validation_metrics,
)

# El entrenamiento dura segundos (ADR-022). El arrendamiento solo evita que un
# proceso caído deje el ciclo bloqueado para siempre.
_LEASE = timedelta(minutes=15)


@dataclass(frozen=True)
class TrainOutcome:
    started: bool
    promoted: bool
    version_id: str | None
    accuracy: float | None
    macro_f1: float | None
    single_example_labels: tuple[str, ...]


class RetrainModel:
    def __init__(
        self,
        entries: KnowledgeEntryRepositoryPort,
        reviews: ReviewedConversationPort,
        trainer: ModelTrainer,
        versions: ModelVersionRepository,
        clock: ClockPort,
    ) -> None:
        self._entries = entries
        self._reviews = reviews
        self._trainer = trainer
        self._versions = versions
        self._clock = clock

    async def execute(self) -> TrainOutcome:
        now = self._clock.now()
        if not await self._versions.try_acquire(now, now + _LEASE):
            return TrainOutcome(False, False, None, None, None, ())
        try:
            return await self._train(now)
        finally:
            await self._versions.release()

    async def _train(self, now: datetime) -> TrainOutcome:
        examples = await self._examples()
        train, validation, singles = split_examples(examples)
        if len(train) == 0:
            return TrainOutcome(True, False, None, None, None, singles)
        model = self._trainer.train(train)
        guesses = tuple(model.predict(text)[0] or "" for _label, text in validation)
        metrics = validation_metrics(tuple(label for label, _text in validation), guesses)
        version = ModelVersion(
            id=str(uuid4()),
            state="CANDIDATE",
            accuracy=metrics.accuracy,
            macro_f1=metrics.macro_f1,
            metrics=metrics,
            single_example_labels=singles,
            artifact=model.artifact(),
            created_at=now,
        )
        await self._versions.add_candidate(version)
        current = await self._versions.active()
        active_f1 = None if current is None else current.macro_f1
        promoted = should_promote(metrics, active_f1)
        if promoted:
            await self._versions.promote(version.id)
        return TrainOutcome(
            True,
            promoted,
            version.id,
            metrics.accuracy,
            metrics.macro_f1,
            singles,
        )

    async def _examples(self) -> tuple[tuple[str, str], ...]:
        rows = list(dictionary_examples(await self._entries.list_all()))
        for turn in await self._reviews.list_reviewed():
            example = conversation_example(turn)
            if example is not None:
                rows.append(example)
        return tuple(rows)
