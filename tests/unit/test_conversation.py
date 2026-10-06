"""Historial de sesion, redaccion y rechazos. No entrena el modelo."""

from datetime import UTC, datetime

import pytest

from chatbot.adapters.outbound.system.fernet_cipher import FernetTextCipher
from chatbot.application.answer import Answer
from chatbot.application.conversation import ConversationSession, RateLimitExceededError
from chatbot.domain.message_guard import (
    InappropriateContentError,
    InjectionAttemptError,
    assert_acceptable,
    redact_sensitive,
)

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


def _session(limit: int = 30) -> tuple[ConversationSession, FernetTextCipher]:
    cipher = FernetTextCipher(FernetTextCipher.generate_key())
    session = ConversationSession(_Answers(), _Clock(), cipher, limit=limit)  # type: ignore[arg-type]
    return session, cipher


async def test_no_guarda_la_contrasena_ni_la_tarjeta() -> None:
    session, cipher = _session()
    actor = "visitor:uno"
    await session.ask(actor, "mi password=secreto123 y tarjeta 4111111111111111", None)
    stored = session._turns[actor][0]
    assert "secreto123" not in stored
    assert "4111" not in stored
    assert cipher.decrypt(stored) != stored
    assert session.history(actor)[0].question == "mi [redactado] y tarjeta [redactado]"


def test_redacta_aunque_no_haya_sesion() -> None:
    assert redact_sensitive("clave: abc") == "[redactado]"


def test_rechaza_inyeccion_y_contenido_ofensivo() -> None:
    with pytest.raises(InjectionAttemptError):
        assert_acceptable("<script>alert(1)</script>")
    with pytest.raises(InappropriateContentError):
        assert_acceptable("eres un malparido")
    assert_acceptable("computadora")


async def test_el_limite_rechaza_la_consulta_31() -> None:
    session, _cipher = _session(limit=2)
    await session.ask("visitor:uno", "hola", None)
    await session.ask("visitor:uno", "hola", None)
    with pytest.raises(RateLimitExceededError):
        await session.ask("visitor:uno", "hola", None)


async def test_limpiar_borra_el_historial_de_esa_sesion() -> None:
    session, _cipher = _session()
    visitor = session.open_visitor_session(None)
    actor = f"visitor:{visitor}"
    await session.ask(actor, "cuanto dura un turno", None)
    assert len(session.history(actor)) == 1
    session.clear(actor)
    assert session.history(actor) == ()
    another = session.open_visitor_session(None)
    assert another != visitor
