"""Historial por persona y limite de consultas (HU-47.3 y HU-51).

El texto se guarda cifrado. El limite es en memoria, una sola replica
(ADR-019). El historial de una persona no se lee para otra.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from chatbot.application.answer import Answer, AnswerQuestion
from chatbot.application.ports.clock import ClockPort
from chatbot.application.ports.transcript_repository import StoredTurn, TranscriptRepository
from chatbot.domain.errors import DomainError
from chatbot.domain.message_guard import assert_acceptable, redact_sensitive


class RateLimitExceededError(DomainError):
    """Demasiadas consultas en la ventana."""


class TextCipherPort(Protocol):
    def encrypt(self, text: str) -> str: ...

    def decrypt(self, token: str) -> str: ...


@dataclass(frozen=True)
class TranscriptTurn:
    id: str
    question: str
    answer: str | None
    model_version: str | None = None
    useful: bool | None = None
    language: str | None = None
    intent: str | None = None


@dataclass(frozen=True)
class RatingOutcome:
    found: bool
    conflict: bool
    newly_rated: bool
    useful: bool | None
    model_version: str | None


class ConversationSession:
    def __init__(
        self,
        answers: AnswerQuestion,
        clock: ClockPort,
        cipher: TextCipherPort,
        transcripts: TranscriptRepository,
        *,
        limit: int = 30,
        window_seconds: int = 60,
    ) -> None:
        self._answers = answers
        self._clock = clock
        self._cipher = cipher
        self._transcripts = transcripts
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def open_visitor_session(self, session_id: str | None) -> str:
        if session_id is not None and await self._transcripts.visitor_known(session_id):
            return session_id
        fresh = str(uuid4())
        await self._transcripts.remember_visitor(fresh)
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
    ) -> tuple[Answer, str]:
        self.allow(actor)
        assert_acceptable(text)
        stored_question = redact_sensitive(text)
        answer = await self._answers.execute(
            stored_question,
            view,
            actor,
            access_token=access_token,
        )
        turn_id = str(uuid4())
        await self._transcripts.add(
            actor,
            StoredTurn(
                id=turn_id,
                question=self._cipher.encrypt(stored_question),
                answer=None if answer.answer is None else self._cipher.encrypt(answer.answer),
                language=answer.language,
                intent=answer.intent,
                model_version=answer.model_version,
                useful=None,
                created_at=self._clock.now(),
            ),
        )
        return answer, turn_id

    async def history(self, actor: str) -> tuple[TranscriptTurn, ...]:
        turns: list[TranscriptTurn] = []
        for stored in await self._transcripts.list_active(actor):
            answer = None if stored.answer is None else self._cipher.decrypt(stored.answer)
            turns.append(
                TranscriptTurn(
                    stored.id,
                    self._cipher.decrypt(stored.question),
                    answer,
                    stored.model_version,
                    stored.useful,
                    stored.language,
                    stored.intent,
                )
            )
        return tuple(turns)

    async def clear(self, actor: str) -> None:
        await self._transcripts.clear(actor)

    async def rate(self, actor: str, turn_id: str, useful: bool) -> RatingOutcome:
        current = await self._transcripts.get(actor, turn_id)
        if current is None:
            return RatingOutcome(False, False, False, None, None)
        if current.useful is not None and current.useful != useful:
            return RatingOutcome(True, True, False, current.useful, current.model_version)
        if current.useful == useful:
            return RatingOutcome(True, False, False, useful, current.model_version)
        updated = await self._transcripts.set_useful(actor, turn_id, useful)
        if updated is None:
            return RatingOutcome(False, False, False, None, None)
        return RatingOutcome(True, False, True, useful, updated.model_version)

    async def show_time(self, actor: str) -> bool:
        stored = await self._transcripts.show_time(actor)
        return True if stored is None else stored

    async def set_show_time(self, actor: str, show_time: bool) -> None:
        await self._transcripts.set_show_time(actor, show_time)
