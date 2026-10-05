"""Puerto del diccionario. La aplicacion no elige memoria ni PostgreSQL."""

from typing import Protocol

from chatbot.domain.knowledge_entry import KnowledgeEntry


class KnowledgeEntryRepositoryPort(Protocol):
    async def add(self, entry: KnowledgeEntry) -> None: ...

    async def save(self, entry: KnowledgeEntry) -> bool: ...

    async def remove(self, entry_id: str) -> bool: ...

    async def get(self, entry_id: str) -> KnowledgeEntry | None: ...

    async def list_all(self) -> tuple[KnowledgeEntry, ...]: ...
