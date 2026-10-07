"""La acción asistida es un camino, no una ejecución."""

import pytest

from chatbot.application.answer import AnswerQuestion
from chatbot.domain.knowledge_entry import knowledge_entry

pytestmark = pytest.mark.anyio


class _Entries:
    async def list_all(self) -> tuple[object, ...]:
        return (
            knowledge_entry(
                entry_id="00000000-0000-4000-8000-000000000081",
                intent="cuenta_gestion",
                language="es",
                priority=1,
                answer="La cuenta se gestiona en su pantalla.",
                variations=("llevame a la cuenta",),
            ),
            knowledge_entry(
                entry_id="00000000-0000-4000-8000-000000000082",
                intent="regla_turno",
                language="es",
                priority=1,
                answer="30 segundos.",
                variations=("cuanto dura un turno",),
            ),
        )


class _Model:
    def __init__(self, label: str) -> None:
        self._label = label

    def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
        del text
        return self._label, 0.9, ()


class _Factory:
    def __init__(self, label: str) -> None:
        self._label = label

    def train(self, examples: tuple[tuple[str, str], ...]) -> _Model:
        del examples
        return _Model(self._label)


async def test_la_cuenta_indica_el_camino_y_no_la_cambia() -> None:
    answer = await AnswerQuestion(_Entries(), _Factory("es:cuenta_gestion")).execute(  # type: ignore[arg-type]
        "llevame a la cuenta",
        None,
    )
    assert answer.answer == "La cuenta se gestiona en su pantalla."
    assert answer.assisted_action == ("configuracion_cuenta", "/account")


async def test_una_regla_no_abre_ninguna_pantalla() -> None:
    answer = await AnswerQuestion(_Entries(), _Factory("es:regla_turno")).execute(  # type: ignore[arg-type]
        "cuanto dura",
        None,
    )
    assert answer.assisted_action is None
