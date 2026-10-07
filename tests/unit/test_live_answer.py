"""Los datos vivos salen del /me del token. Si falta, no se inventan."""

import pytest

from chatbot.application.answer import AnswerQuestion
from chatbot.domain.knowledge_entry import knowledge_entry

pytestmark = pytest.mark.anyio


class _Entries:
    async def list_all(self) -> tuple[object, ...]:
        return (
            knowledge_entry(
                entry_id="00000000-0000-4000-8000-000000000071",
                intent="regla_turno",
                language="es",
                priority=1,
                answer="30 segundos.",
                variations=("cuanto dura un turno",),
            ),
            knowledge_entry(
                entry_id="00000000-0000-4000-8000-000000000072",
                intent="mi_inventario",
                language="es",
                priority=1,
                answer="plantilla",
                variations=("que tengo en el inventario",),
            ),
        )


class _Model:
    def __init__(self, label: str, confidence: float = 0.9) -> None:
        self._label = label
        self._confidence = confidence

    def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
        del text
        return self._label, self._confidence, ()


class _Factory:
    def __init__(self, label: str, confidence: float = 0.9) -> None:
        self._label = label
        self._confidence = confidence

    def train(self, examples: tuple[tuple[str, str], ...]) -> _Model:
        del examples
        return _Model(self._label, self._confidence)


class _Player:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    async def fetch(self, source: str, access_token: str) -> dict[str, object] | None:
        self.calls.append((source, access_token))
        return self.payload


async def test_el_inventario_usa_el_token_y_el_total_real() -> None:
    player = _Player(
        {
            "totalItems": 1,
            "items": [{"quantity": 2, "product": {"name": "Espada de Hierro"}}],
        }
    )
    question = AnswerQuestion(
        _Entries(),  # type: ignore[arg-type]
        _Factory("es:mi_inventario"),
        player_data=player,
    )
    answer = await question.execute("que tengo", None, access_token="token-del-jugador")
    assert answer.answer == ("El inventario tiene 1 objeto. En esta página: Espada de Hierro x 2.")
    assert player.calls == [("inventory", "token-del-jugador")]


async def test_un_dato_propio_dudoso_no_pide_sesion() -> None:
    player = _Player({"totalItems": 1, "items": []})
    question = AnswerQuestion(
        _Entries(),  # type: ignore[arg-type]
        _Factory("es:mi_inventario", 0.2),
        player_data=player,
    )
    answer = await question.execute("el trafico de hoy", None)
    assert answer.answered is False
    assert answer.answer is None
    assert player.calls == []


async def test_sin_sesion_no_consulta_el_servicio() -> None:
    player = _Player({"totalItems": 1, "items": []})
    question = AnswerQuestion(
        _Entries(),  # type: ignore[arg-type]
        _Factory("es:mi_inventario"),
        player_data=player,
    )
    answer = await question.execute("que tengo", None)
    assert answer.answer == "Inicia sesión para consultar tus datos."
    assert player.calls == []


async def test_si_el_servicio_falla_no_inventa_el_dato() -> None:
    player = _Player(None)
    question = AnswerQuestion(
        _Entries(),  # type: ignore[arg-type]
        _Factory("es:mi_mision"),
        player_data=player,
    )
    answer = await question.execute("mis misiones", None, access_token="token-del-jugador")
    assert answer.answer == "No pude consultar ese dato ahora."
    assert "0" not in (answer.answer or "")


async def test_el_torneo_no_tiene_consulta_propia() -> None:
    player = _Player({"items": []})
    question = AnswerQuestion(
        _Entries(),  # type: ignore[arg-type]
        _Factory("es:mi_torneo"),
        player_data=player,
    )
    answer = await question.execute("mi torneo", None, access_token="token-del-jugador")
    assert answer.answer == "No pude consultar ese dato ahora."
    assert player.calls == []
