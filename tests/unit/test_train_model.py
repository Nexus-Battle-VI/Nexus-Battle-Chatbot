"""El ciclo de promoción no depende de scikit-learn: el modelo es un puerto."""

from datetime import UTC, datetime

import pytest

from chatbot.adapters.outbound.persistence.in_memory_knowledge import (
    InMemoryKnowledgeEntryRepository,
)
from chatbot.adapters.outbound.persistence.in_memory_versions import (
    InMemoryModelVersionRepository,
)
from chatbot.application.answer import AnswerQuestion
from chatbot.application.ports.intent_model import IntentModel
from chatbot.application.ports.model_version_repository import ModelVersion
from chatbot.application.train_model import RetrainModel
from chatbot.domain.knowledge_entry import knowledge_entry
from chatbot.domain.training_set import ConversationTurn, ValidationMetrics

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 10, 5, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _Reviews:
    def __init__(self, turns: tuple[ConversationTurn, ...]) -> None:
        self._turns = turns

    async def list_reviewed(self) -> tuple[ConversationTurn, ...]:
        return self._turns


class _Model:
    def __init__(self, labels: dict[str, str]) -> None:
        self._labels = labels

    def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
        return self._labels.get(text, "es:otra"), 0.99, ()

    def artifact(self) -> bytes:
        return b"modelo"


class _Trainer:
    def __init__(self, labels: dict[str, str]) -> None:
        self._labels = labels
        self.trained: tuple[tuple[str, str], ...] = ()

    def train(self, examples: tuple[tuple[str, str], ...]) -> _Model:
        self.trained = examples
        return _Model(self._labels)

    def load(self, artifact: bytes) -> _Model:
        del artifact
        return _Model(self._labels)


def _labels_for(*pairs: tuple[str, str]) -> dict[str, str]:
    return {text: label for label, text in pairs}


async def _entries() -> InMemoryKnowledgeEntryRepository:
    repository = InMemoryKnowledgeEntryRepository()
    await repository.add(
        knowledge_entry(
            entry_id="00000000-0000-4000-8000-000000000021",
            intent="regla_turno",
            language="es",
            priority=1,
            answer="30 segundos.",
            variations=("alfa uno", "alfa dos", "alfa tres", "alfa cuatro", "alfa cinco"),
        )
    )
    await repository.add(
        knowledge_entry(
            entry_id="00000000-0000-4000-8000-000000000022",
            intent="cuenta",
            language="es",
            priority=1,
            answer="En preferencias.",
            variations=("beta uno", "beta dos", "beta tres", "beta cuatro", "beta cinco"),
        )
    )
    return repository


async def test_la_primera_version_que_acierta_queda_activa() -> None:
    entries = await _entries()
    labels = _labels_for(
        ("es:regla_turno", "alfa uno"),
        ("es:regla_turno", "alfa dos"),
        ("es:regla_turno", "alfa tres"),
        ("es:regla_turno", "alfa cuatro"),
        ("es:regla_turno", "alfa cinco"),
        ("es:cuenta", "beta uno"),
        ("es:cuenta", "beta dos"),
        ("es:cuenta", "beta tres"),
        ("es:cuenta", "beta cuatro"),
        ("es:cuenta", "beta cinco"),
    )
    versions = InMemoryModelVersionRepository()
    trainer = _Trainer(labels)
    outcome = await RetrainModel(entries, _Reviews(()), trainer, versions, _Clock()).execute()
    assert outcome.promoted is True
    active = await versions.active()
    assert active is not None
    assert active.id == outcome.version_id
    assert active.state == "ACTIVE"
    assert active.accuracy == 1.0


async def test_una_candidata_que_no_mejora_no_sustituye_a_la_activa() -> None:
    entries = await _entries()
    versions = InMemoryModelVersionRepository()
    good = _labels_for(
        ("es:regla_turno", "alfa uno"),
        ("es:regla_turno", "alfa dos"),
        ("es:regla_turno", "alfa tres"),
        ("es:regla_turno", "alfa cuatro"),
        ("es:regla_turno", "alfa cinco"),
        ("es:cuenta", "beta uno"),
        ("es:cuenta", "beta dos"),
        ("es:cuenta", "beta tres"),
        ("es:cuenta", "beta cuatro"),
        ("es:cuenta", "beta cinco"),
    )
    job = RetrainModel(entries, _Reviews(()), _Trainer(good), versions, _Clock())
    await job.execute()
    current = await versions.active()
    assert current is not None
    failed_job = RetrainModel(entries, _Reviews(()), _Trainer({}), versions, _Clock())
    failed = await failed_job.execute()
    assert failed.promoted is False
    assert failed.version_id is not None
    assert (await versions.active()).id == current.id  # type: ignore[union-attr]


async def test_una_candidata_que_sigue_acertando_puede_promoverse() -> None:
    entries = await _entries()
    versions = InMemoryModelVersionRepository()
    labels = _labels_for(
        ("es:regla_turno", "alfa uno"),
        ("es:regla_turno", "alfa dos"),
        ("es:regla_turno", "alfa tres"),
        ("es:regla_turno", "alfa cuatro"),
        ("es:regla_turno", "alfa cinco"),
        ("es:cuenta", "beta uno"),
        ("es:cuenta", "beta dos"),
        ("es:cuenta", "beta tres"),
        ("es:cuenta", "beta cuatro"),
        ("es:cuenta", "beta cinco"),
    )
    trainer = _Trainer(labels)
    first_job = RetrainModel(entries, _Reviews(()), trainer, versions, _Clock())
    second_job = RetrainModel(entries, _Reviews(()), trainer, versions, _Clock())
    first = await first_job.execute()
    second = await second_job.execute()
    assert second.promoted is True
    assert (await versions.active()).id == second.version_id  # type: ignore[union-attr]
    assert second.version_id != first.version_id


async def test_la_conversacion_util_entra_y_el_resto_no() -> None:
    entries = await _entries()
    trainer = _Trainer({})
    reviews = _Reviews(
        (
            ConversationTurn("como cambio el correo", "es", "correo", True, False),
            ConversationTurn("esto no sirvio", "es", "cuenta", False, False),
            ConversationTurn("todavia no", "es", "cuenta", None, False),
            ConversationTurn("borrada", "es", "cuenta", True, True),
        )
    )
    versions = InMemoryModelVersionRepository()
    job = RetrainModel(entries, reviews, trainer, versions, _Clock())
    outcome = await job.execute()
    trained_texts = {text for _label, text in trainer.trained}
    assert ("es:correo", "como cambio el correo") in trainer.trained
    assert "esto no sirvio" not in trained_texts
    assert "todavia no" not in trained_texts
    assert "borrada" not in trained_texts
    assert "es:correo" in outcome.single_example_labels


async def test_un_ciclo_en_curso_no_arranca_otro() -> None:
    versions = InMemoryModelVersionRepository()
    assert await versions.try_acquire(_NOW, _NOW.replace(minute=15)) is True
    entries = await _entries()
    blocked = RetrainModel(entries, _Reviews(()), _Trainer({}), versions, _Clock())
    outcome = await blocked.execute()
    assert outcome.started is False
    await versions.release()


async def test_la_version_activa_responde_sin_reentrenar() -> None:
    class _Fixed(IntentModel):
        def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
            del text
            return "es:regla_turno", 0.9, ()

    class _Loader:
        def train(self, examples: tuple[tuple[str, str], ...]) -> _Fixed:
            del examples
            return _Fixed()

        def load(self, artifact: bytes) -> _Fixed:
            del artifact
            return _Fixed()

    class _Factory:
        def __init__(self) -> None:
            self.trains = 0

        def train(self, examples: tuple[tuple[str, str], ...]) -> _Fixed:
            del examples
            self.trains += 1
            return _Fixed()

    versions = InMemoryModelVersionRepository()
    await versions.add_candidate(
        ModelVersion(
            id="00000000-0000-4000-8000-000000000099",
            state="CANDIDATE",
            accuracy=1.0,
            macro_f1=1.0,
            metrics=ValidationMetrics(1.0, 1.0, (), ()),
            single_example_labels=(),
            artifact=b"modelo",
            created_at=_NOW,
        )
    )
    await versions.promote("00000000-0000-4000-8000-000000000099")
    entries = await _entries()
    factory = _Factory()
    answer = await AnswerQuestion(entries, factory, versions, _Loader()).execute("alfa uno", None)
    assert factory.trains == 0
    assert answer.answered is True
    assert answer.answer == "30 segundos."
