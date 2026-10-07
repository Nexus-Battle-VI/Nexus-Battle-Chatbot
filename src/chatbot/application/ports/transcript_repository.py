"""Historial de una persona. El texto ya va cifrado; la clave no vive aquí."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class StoredTurn:
    id: str
    question: str
    answer: str | None
    language: str | None
    intent: str | None
    model_version: str | None
    useful: bool | None
    created_at: datetime
    duration_ms: int | None = None


class TranscriptRepository(Protocol):
    async def add(self, actor: str, turn: StoredTurn) -> None: ...

    async def list_active(self, actor: str) -> tuple[StoredTurn, ...]: ...

    async def get(self, actor: str, turn_id: str) -> StoredTurn | None: ...

    async def clear(self, actor: str) -> None: ...

    async def set_useful(self, actor: str, turn_id: str, useful: bool) -> StoredTurn | None: ...

    async def list_rated(self) -> tuple[StoredTurn, ...]: ...

    async def list_between(self, start: datetime, end: datetime) -> tuple[StoredTurn, ...]: ...

    async def count_started(self, start: datetime, end: datetime) -> int: ...

    async def remember_visitor(self, session_id: str) -> None: ...

    async def visitor_known(self, session_id: str) -> bool: ...

    async def show_time(self, actor: str) -> bool | None: ...

    async def set_show_time(self, actor: str, show_time: bool) -> None: ...
