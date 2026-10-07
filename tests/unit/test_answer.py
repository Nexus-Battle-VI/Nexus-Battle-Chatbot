"""La decision de responder no depende de scikit-learn: el modelo es un puerto."""

import pytest

from chatbot.application.answer import AnswerQuestion
from chatbot.domain.knowledge_entry import knowledge_entry

pytestmark = pytest.mark.anyio


class _Memory:
    def __init__(self) -> None:
        self.entries = (
            knowledge_entry(
                entry_id="00000000-0000-4000-8000-000000000001",
                intent="regla_turno",
                language="es",
                priority=1,
                answer="Cada turno dura 30 segundos.",
                variations=["cuanto dura un turno"],
            ),
            knowledge_entry(
                entry_id="00000000-0000-4000-8000-000000000002",
                intent="modo_mision",
                language="es",
                priority=1,
                answer="La mision bloquea al heroe.",
                variations=["como funciona una mision"],
            ),
            knowledge_entry(
                entry_id="00000000-0000-4000-8000-000000000003",
                intent="modo_mision",
                language="es",
                priority=5,
                answer="En esta vista eliges la dificultad.",
                variations=["como funciona una mision aqui"],
                view="misiones",
            ),
        )

    async def add(self, entry: object) -> None:
        del entry

    async def save(self, entry: object) -> bool:
        del entry
        return True

    async def remove(self, entry_id: str) -> bool:
        del entry_id
        return True

    async def get(self, entry_id: str) -> None:
        del entry_id

    async def list_all(self) -> tuple[object, ...]:
        return self.entries


class _Model:
    def __init__(self, label: str, confidence: float) -> None:
        self._label = label
        self._confidence = confidence

    def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
        del text
        return self._label, self._confidence, ("es:modo_mision",)


class _Factory:
    def __init__(self, label: str, confidence: float) -> None:
        self.trains = 0
        self._label = label
        self._confidence = confidence

    def train(self, examples: tuple[tuple[str, str], ...]) -> _Model:
        del examples
        self.trains += 1
        return _Model(self._label, self._confidence)


async def test_por_debajo_del_umbral_no_hay_respuesta() -> None:
    factory = _Factory("es:regla_turno", 0.4)
    answer = await AnswerQuestion(_Memory(), factory).execute("cualquier cosa", None)  # type: ignore[arg-type]
    assert answer.answered is False
    assert answer.answer is None
    assert answer.suggestions == ("como funciona una mision",)


async def test_la_vista_elige_la_entrada_de_esa_vista() -> None:
    factory = _Factory("es:modo_mision", 0.9)
    answer = await AnswerQuestion(_Memory(), factory).execute("mision", "misiones")  # type: ignore[arg-type]
    assert answer.answered is True
    assert answer.kind == "contextual"
    assert answer.answer == "En esta vista eliges la dificultad."


async def test_la_segunda_pregunta_igual_no_reentrena() -> None:
    factory = _Factory("es:regla_turno", 0.9)
    use_case = AnswerQuestion(_Memory(), factory)  # type: ignore[arg-type]
    await use_case.execute("turno", None)
    await use_case.execute("turno", None)
    assert factory.trains == 1
