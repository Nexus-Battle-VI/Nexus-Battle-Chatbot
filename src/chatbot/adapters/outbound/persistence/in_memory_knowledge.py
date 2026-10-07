"""Diccionario en memoria. Sirve al modo sin PostgreSQL y a las pruebas HTTP."""

from chatbot.domain.knowledge_entry import KnowledgeEntry


class InMemoryKnowledgeEntryRepository:
    def __init__(self) -> None:
        self._entries: dict[str, KnowledgeEntry] = {}

    async def add(self, entry: KnowledgeEntry) -> None:
        self._entries[entry.id] = entry

    async def save(self, entry: KnowledgeEntry) -> bool:
        if entry.id not in self._entries:
            return False
        self._entries[entry.id] = entry
        return True

    async def remove(self, entry_id: str) -> bool:
        return self._entries.pop(entry_id, None) is not None

    async def get(self, entry_id: str) -> KnowledgeEntry | None:
        return self._entries.get(entry_id)

    async def list_all(self) -> tuple[KnowledgeEntry, ...]:
        return tuple(
            sorted(
                self._entries.values(),
                key=lambda entry: (entry.intent, entry.language, -entry.priority, entry.id),
            )
        )
