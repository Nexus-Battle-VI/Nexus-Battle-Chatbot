"""Casos de uso del diccionario (HU-53.1).

Clases planas: no conocen FastAPI ni el motor. El identificador lo genera el
servicio, nunca el cliente.
"""

from uuid import uuid4

from chatbot.application.ports.knowledge_entry_repository import KnowledgeEntryRepositoryPort
from chatbot.domain.errors import DomainError
from chatbot.domain.knowledge_entry import KnowledgeEntry, knowledge_entry


class KnowledgeEntryNotFoundError(DomainError):
    def __init__(self, entry_id: str) -> None:
        super().__init__(f"No existe la entrada {entry_id}.")
        self.entry_id = entry_id


class CreateKnowledgeEntry:
    def __init__(self, entries: KnowledgeEntryRepositoryPort) -> None:
        self._entries = entries

    async def execute(
        self,
        *,
        intent: str,
        language: str,
        priority: int,
        answer: str,
        variations: list[str],
    ) -> KnowledgeEntry:
        entry = knowledge_entry(
            entry_id=str(uuid4()),
            intent=intent,
            language=language,
            priority=priority,
            answer=answer,
            variations=variations,
        )
        await self._entries.add(entry)
        return entry


class UpdateKnowledgeEntry:
    def __init__(self, entries: KnowledgeEntryRepositoryPort) -> None:
        self._entries = entries

    async def execute(
        self,
        entry_id: str,
        *,
        intent: str,
        language: str,
        priority: int,
        answer: str,
        variations: list[str],
    ) -> KnowledgeEntry:
        current = await self._entries.get(entry_id)
        if current is None:
            raise KnowledgeEntryNotFoundError(entry_id)
        entry = knowledge_entry(
            entry_id=current.id,
            intent=intent,
            language=language,
            priority=priority,
            answer=answer,
            variations=variations,
        )
        saved = await self._entries.save(entry)
        if not saved:
            raise KnowledgeEntryNotFoundError(entry_id)
        return entry


class DeleteKnowledgeEntry:
    def __init__(self, entries: KnowledgeEntryRepositoryPort) -> None:
        self._entries = entries

    async def execute(self, entry_id: str) -> None:
        removed = await self._entries.remove(entry_id)
        if not removed:
            raise KnowledgeEntryNotFoundError(entry_id)


class ListKnowledgeEntries:
    """Lista intencion, variaciones y respuesta para reconocimiento y entrenamiento."""

    def __init__(self, entries: KnowledgeEntryRepositoryPort) -> None:
        self._entries = entries

    async def execute(self) -> tuple[KnowledgeEntry, ...]:
        return await self._entries.list_all()
