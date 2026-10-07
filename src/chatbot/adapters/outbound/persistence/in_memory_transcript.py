"""Historial en memoria. Se pierde al reiniciar el proceso."""

from collections import defaultdict
from datetime import datetime

from chatbot.application.ports.transcript_repository import StoredTurn


class InMemoryTranscriptRepository:
    def __init__(self) -> None:
        self._turns: dict[str, list[StoredTurn]] = defaultdict(list)
        self._deleted: set[str] = set()
        self._visitors: set[str] = set()
        self._show_time: dict[str, bool] = {}

    async def add(self, actor: str, turn: StoredTurn) -> None:
        self._turns[actor].append(turn)

    async def list_active(self, actor: str) -> tuple[StoredTurn, ...]:
        return tuple(turn for turn in self._turns.get(actor, []) if turn.id not in self._deleted)

    async def get(self, actor: str, turn_id: str) -> StoredTurn | None:
        for turn in self._turns.get(actor, []):
            if turn.id == turn_id and turn.id not in self._deleted:
                return turn
        return None

    async def clear(self, actor: str) -> None:
        for turn in self._turns.get(actor, []):
            self._deleted.add(turn.id)

    async def set_useful(self, actor: str, turn_id: str, useful: bool) -> StoredTurn | None:
        rows = self._turns.get(actor, [])
        for index, turn in enumerate(rows):
            if turn.id != turn_id or turn.id in self._deleted:
                continue
            updated = StoredTurn(
                turn.id,
                turn.question,
                turn.answer,
                turn.language,
                turn.intent,
                turn.model_version,
                useful,
                turn.created_at,
                turn.duration_ms,
            )
            rows[index] = updated
            return updated
        return None

    async def list_rated(self) -> tuple[StoredTurn, ...]:
        rated: list[StoredTurn] = []
        for rows in self._turns.values():
            for turn in rows:
                if turn.id not in self._deleted and turn.useful is not None:
                    rated.append(turn)
        return tuple(rated)

    async def list_between(self, start: datetime, end: datetime) -> tuple[StoredTurn, ...]:
        found = [turn for _actor, turn in self._visible() if start <= turn.created_at <= end]
        found.sort(key=lambda turn: (turn.created_at, turn.id))
        return tuple(found)

    async def count_started(self, start: datetime, end: datetime) -> int:
        first: dict[str, datetime] = {}
        for actor, turn in self._visible():
            current = first.get(actor)
            if current is None or turn.created_at < current:
                first[actor] = turn.created_at
        return sum(1 for moment in first.values() if start <= moment <= end)

    def _visible(self) -> tuple[tuple[str, StoredTurn], ...]:
        rows: list[tuple[str, StoredTurn]] = []
        for actor, turns in self._turns.items():
            for turn in turns:
                if turn.id not in self._deleted:
                    rows.append((actor, turn))
        return tuple(rows)

    async def remember_visitor(self, session_id: str) -> None:
        self._visitors.add(session_id)

    async def visitor_known(self, session_id: str) -> bool:
        return session_id in self._visitors

    async def show_time(self, actor: str) -> bool | None:
        return self._show_time.get(actor)

    async def set_show_time(self, actor: str, show_time: bool) -> None:
        self._show_time[actor] = show_time
