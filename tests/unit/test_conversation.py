"""Historial de sesion, redaccion y rechazos. No entrena el modelo."""

from datetime import UTC, datetime

import pytest

from chatbot.adapters.outbound.persistence.in_memory_transcript import (
    InMemoryTranscriptRepository,
)
from chatbot.adapters.outbound.system.fernet_cipher import FernetTextCipher
from chatbot.application.answer import Answer
from chatbot.application.conversation import ConversationSession, RateLimitExceededError
from chatbot.application.reviewed_transcript import ReviewedTranscript
from chatbot.domain.message_guard import (
    InappropriateContentError,
    InjectionAttemptError,
    assert_acceptable,
    redact_sensitive,
)
from chatbot.domain.training_set import conversation_example

pytestmark = pytest.mark.anyio


class _Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.moment


class _Answers:
    async def execute(
        self,
        text: str,
        view: str | None,
        actor: str | None = None,
        **_extra: object,
    ) -> Answer:
        del actor
        return Answer(True, "regla_turno", "es", 0.9, "30 segundos", "direct", (), view)


def _session(
    limit: int = 30,
) -> tuple[ConversationSession, FernetTextCipher, InMemoryTranscriptRepository]:
    cipher = FernetTextCipher(FernetTextCipher.generate_key())
    store = InMemoryTranscriptRepository()
    session = ConversationSession(_Answers(), _Clock(), cipher, store, limit=limit)  # type: ignore[arg-type]
    return session, cipher, store


async def test_no_guarda_la_contrasena_ni_la_tarjeta() -> None:
    session, cipher, store = _session()
    actor = "visitor:uno"
    await session.ask(actor, "mi password=secreto123 y tarjeta 4111111111111111", None)
    stored = (await store.list_active(actor))[0]
    assert "secreto123" not in stored.question
    assert "4111" not in stored.question
    assert cipher.decrypt(stored.question) == "mi [redactado] y tarjeta [redactado]"
    assert (await session.history(actor))[0].question == "mi [redactado] y tarjeta [redactado]"


def test_redacta_aunque_no_haya_sesion() -> None:
    assert redact_sensitive("clave: abc") == "[redactado]"


def test_rechaza_inyeccion_y_contenido_ofensivo() -> None:
    with pytest.raises(InjectionAttemptError):
        assert_acceptable("<script>alert(1)</script>")
    with pytest.raises(InappropriateContentError):
        assert_acceptable("eres un malparido")
    assert_acceptable("computadora")


async def test_el_limite_rechaza_la_consulta_31() -> None:
    session, _cipher, _store = _session(limit=2)
    await session.ask("visitor:uno", "hola", None)
    await session.ask("visitor:uno", "hola", None)
    with pytest.raises(RateLimitExceededError):
        await session.ask("visitor:uno", "hola", None)


async def test_limpiar_borra_el_historial_de_esa_sesion() -> None:
    session, _cipher, _store = _session()
    visitor = await session.open_visitor_session(None)
    actor = f"visitor:{visitor}"
    await session.ask(actor, "cuanto dura un turno", None)
    assert len(await session.history(actor)) == 1
    await session.clear(actor)
    assert await session.history(actor) == ()
    another = await session.open_visitor_session(None)
    assert another != visitor


async def test_una_valoracion_util_entra_al_conjunto_de_su_dueno() -> None:
    session, cipher, store = _session()
    _answer, turn_id = await session.ask("player:uno", "cuanto dura un turno", None)
    assert await session.history("player:dos") == ()
    outcome = await session.rate("player:uno", turn_id, True)
    assert outcome.newly_rated is True
    reviewed = await ReviewedTranscript(store, cipher).list_reviewed()
    example = conversation_example(reviewed[0])
    assert example is not None
    assert example[0] == "es:regla_turno"
    await session.clear("player:uno")
    assert await ReviewedTranscript(store, cipher).list_reviewed() == ()
