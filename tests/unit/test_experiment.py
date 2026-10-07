"""El reparto A/B no cambia de versión dentro de la misma sesión."""

from datetime import UTC, datetime

import pytest

from chatbot.adapters.outbound.persistence.in_memory_knowledge import (
    InMemoryKnowledgeEntryRepository,
)
from chatbot.adapters.outbound.persistence.in_memory_versions import (
    InMemoryModelVersionRepository,
)
from chatbot.application.answer import AnswerQuestion
from chatbot.application.ports.model_version_repository import ModelVersion
from chatbot.application.precision import ReadModelPrecision
from chatbot.domain.experiment import live_precision, sees_candidate
from chatbot.domain.knowledge_entry import knowledge_entry
from chatbot.domain.training_set import ValidationMetrics

pytestmark = pytest.mark.anyio

_NOW = datetime(2026, 10, 5, tzinfo=UTC)


class _Model:
    def __init__(self, label: str) -> None:
        self._label = label

    def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
        del text
        return self._label, 0.9, ()


class _Loader:
    def train(self, examples: tuple[tuple[str, str], ...]) -> _Model:
        del examples
        return _Model("es:regla_turno")

    def load(self, artifact: bytes) -> _Model:
        label = "es:cuenta" if artifact == b"candidata" else "es:regla_turno"
        return _Model(label)


def _version(version_id: str, artifact: bytes) -> ModelVersion:
    return ModelVersion(
        id=version_id,
        state="CANDIDATE",
        accuracy=1.0,
        macro_f1=1.0,
        metrics=ValidationMetrics(1.0, 1.0, (), ()),
        single_example_labels=(),
        artifact=artifact,
        created_at=_NOW,
    )


async def _ready() -> tuple[InMemoryKnowledgeEntryRepository, InMemoryModelVersionRepository]:
    entries = InMemoryKnowledgeEntryRepository()
    await entries.add(
        knowledge_entry(
            entry_id="00000000-0000-4000-8000-000000000041",
            intent="regla_turno",
            language="es",
            priority=1,
            answer="30 segundos.",
            variations=("alfa uno",),
        )
    )
    await entries.add(
        knowledge_entry(
            entry_id="00000000-0000-4000-8000-000000000042",
            intent="cuenta",
            language="es",
            priority=1,
            answer="En preferencias.",
            variations=("beta uno",),
        )
    )
    versions = InMemoryModelVersionRepository()
    await versions.add_candidate(_version("00000000-0000-4000-8000-0000000000a1", b"activa"))
    await versions.promote("00000000-0000-4000-8000-0000000000a1")
    await versions.add_candidate(_version("00000000-0000-4000-8000-0000000000c1", b"candidata"))
    assert await versions.mark_experiment("00000000-0000-4000-8000-0000000000c1") is True
    return entries, versions


def test_sin_porcentaje_nadie_ve_a_la_candidata() -> None:
    assert sees_candidate("visitor:1", 0) is False
    assert sees_candidate("visitor:1", 100) is True
    assert sees_candidate("visitor:1", 50) is sees_candidate("visitor:1", 50)
    assert live_precision(0, 0) is None
    assert live_precision(2, 1) == 2 / 3


def _pair() -> tuple[str, str]:
    seen = unseen = None
    for index in range(400):
        actor = f"visitor:{index}"
        if sees_candidate(actor, 50):
            seen = actor
        else:
            unseen = actor
        if seen is not None and unseen is not None:
            return seen, unseen
    raise AssertionError("no hubo dos sesiones en cubetas distintas")


async def test_el_reparto_cambia_entre_sesiones_y_no_dentro_de_una() -> None:
    entries, versions = await _ready()
    seen, unseen = _pair()
    answers = AnswerQuestion(entries, _Loader(), versions, _Loader(), 50)
    first = await answers.execute("alfa", None, seen)
    again = await answers.execute("alfa", None, seen)
    other = await answers.execute("alfa", None, unseen)
    assert first.model_version == again.model_version
    assert first.model_version != other.model_version
    assert {first.answer, other.answer} == {"30 segundos.", "En preferencias."}


async def test_con_porcentaje_cero_todas_usan_la_activa() -> None:
    entries, versions = await _ready()
    answers = AnswerQuestion(entries, _Loader(), versions, _Loader(), 0)
    seen, unseen = _pair()
    first = await answers.execute("alfa", None, seen)
    second = await answers.execute("alfa", None, unseen)
    assert first.model_version == second.model_version == "00000000-0000-4000-8000-0000000000a1"
    assert first.answer == "30 segundos."


async def test_la_precision_ignora_lo_que_no_se_valoro() -> None:
    _entries, versions = await _ready()
    active = "00000000-0000-4000-8000-0000000000a1"
    await versions.record_answer(active, None)
    assert (await ReadModelPrecision(versions).execute())[0].precision is None
    await versions.record_answer(active, True)
    await versions.record_answer(active, True)
    await versions.record_answer(active, False)
    rows = await ReadModelPrecision(versions).execute()
    active_row = next(row for row in rows if row.version_id == active)
    assert active_row.useful == 2
    assert active_row.not_useful == 1
    assert active_row.precision == 2 / 3
