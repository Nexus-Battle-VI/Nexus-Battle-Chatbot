"""Historial en memoria. Se pierde al reiniciar el proceso."""

from collections import defaultdict

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

    async def remember_visitor(self, session_id: str) -> None:
        self._visitors.add(session_id)

    async def visitor_known(self, session_id: str) -> bool:
        return session_id in self._visitors

    async def show_time(self, actor: str) -> bool | None:
        return self._show_time.get(actor)

    async def set_show_time(self, actor: str, show_time: bool) -> None:
        self._show_time[actor] = show_time
