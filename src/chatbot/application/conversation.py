"""Historial de una sola sesion y limite de consultas (HU-47.3).

No conserva la conversacion entre sesiones: eso es HU-51. Lo que se guarda
esta cifrado. El limite es en memoria, una sola replica (ADR-019).
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from chatbot.application.answer import Answer, AnswerQuestion
from chatbot.application.ports.clock import ClockPort
from chatbot.domain.errors import DomainError
from chatbot.domain.message_guard import assert_acceptable, redact_sensitive


class RateLimitExceededError(DomainError):
    """Demasiadas consultas en la ventana."""


class TextCipherPort(Protocol):
    def encrypt(self, text: str) -> str: ...

    def decrypt(self, token: str) -> str: ...


@dataclass(frozen=True)
class TranscriptTurn:
    question: str
    answer: str | None
    model_version: str | None = None


class ConversationSession:
    def __init__(
        self,
        answers: AnswerQuestion,
        clock: ClockPort,
        cipher: TextCipherPort,
        *,
        limit: int = 30,
        window_seconds: int = 60,
    ) -> None:
        self._answers = answers
        self._clock = clock
        self._cipher = cipher
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._issued: set[str] = set()
        self._turns: dict[str, list[str]] = defaultdict(list)

    def open_visitor_session(self, session_id: str | None) -> str:
        if session_id is not None and session_id in self._issued:
            return session_id
        fresh = str(uuid4())
        self._issued.add(fresh)
        return fresh

    def allow(self, actor: str) -> None:
        now = self._clock.now().timestamp()
        recent = [moment for moment in self._hits[actor] if now - moment < self._window]
        if len(recent) >= self._limit:
            self._hits[actor] = recent
            raise RateLimitExceededError("Demasiadas consultas. Espera un momento.")
        recent.append(now)
        self._hits[actor] = recent

    async def ask(
        self,
        actor: str,
        text: str,
        view: str | None,
        access_token: str | None = None,
    ) -> Answer:
        self.allow(actor)
        assert_acceptable(text)
        stored_question = redact_sensitive(text)
        answer = await self._answers.execute(
            stored_question,
            view,
            actor,
            access_token=access_token,
        )
        self._remember(actor, stored_question, answer.answer, answer.model_version)
        return answer

    def history(self, actor: str) -> tuple[TranscriptTurn, ...]:
        turns: list[TranscriptTurn] = []
        for token in self._turns.get(actor, []):
            plain = self._cipher.decrypt(token)
            question, separator, rest = plain.partition("\n---\n")
            if separator == "":
                turns.append(TranscriptTurn(question, None))
                continue
            reply, version_separator, version = rest.partition("\n---\n")
            stored_answer = None if version_separator and reply == "" else reply
            turns.append(
                TranscriptTurn(
                    question,
                    stored_answer,
                    version if version_separator else None,
                )
            )
        return tuple(turns)

    def clear(self, actor: str) -> None:
        self._turns.pop(actor, None)

    def _remember(
        self,
        actor: str,
        question: str,
        answer: str | None,
        model_version: str | None,
    ) -> None:
        if model_version is None:
            payload = question if answer is None else f"{question}\n---\n{answer}"
        else:
            reply = "" if answer is None else answer
            payload = f"{question}\n---\n{reply}\n---\n{model_version}"
        self._turns[actor].append(self._cipher.encrypt(payload))
