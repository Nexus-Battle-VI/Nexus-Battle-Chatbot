"""Casos de uso del diccionario (HU-53.1).

Clases planas: no conocen FastAPI ni el motor. El identificador lo genera el
servicio, nunca el cliente.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from chatbot.application.ports.knowledge_entry_repository import KnowledgeEntryRepositoryPort
from chatbot.domain.errors import DomainError, InvalidKnowledgeEntryError
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
        view: str | None = None,
    ) -> KnowledgeEntry:
        entry = knowledge_entry(
            entry_id=str(uuid4()),
            intent=intent,
            language=language,
            priority=priority,
            answer=answer,
            variations=variations,
            view=view,
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
        view: str | None = None,
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
            view=view,
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


@dataclass(frozen=True)
class ImportRow:
    intent: str
    language: str
    priority: int
    answer: str
    variations: tuple[str, ...]
    question: str | None = None
    view: str | None = None


class ImportKnowledgeEntries:
    """Carga un documento. Si una entrada ya existe, no la pisa ni la duplica."""

    def __init__(self, entries: KnowledgeEntryRepositoryPort) -> None:
        self._entries = entries

    async def execute(self, rows: tuple[ImportRow, ...]) -> tuple[int, int]:
        prepared = tuple(_imported(row) for row in rows)
        stored = await self._entries.list_all()
        known = {(entry.intent, entry.language, entry.view) for entry in stored}
        created = 0
        skipped = 0
        for entry in prepared:
            key = (entry.intent, entry.language, entry.view)
            if key in known:
                skipped += 1
                continue
            await self._entries.add(entry)
            known.add(key)
            created += 1
        return created, skipped


def export_document(entries: tuple[KnowledgeEntry, ...]) -> dict[str, object]:
    """Documento de esquema 1. La primera variacion viaja como pregunta."""
    rows: list[dict[str, object]] = []
    for entry in entries:
        question, *rest = entry.variations
        rows.append(
            {
                "intent": entry.intent,
                "language": entry.language,
                "priority": entry.priority,
                "question": question,
                "variations": rest,
                "view": entry.view,
            }
        )
    return {"schemaVersion": 1, "entries": rows}


def rows_from_document(document: Mapping[str, object]) -> tuple[ImportRow, ...]:
    """Lee un documento de esquema 1. La semilla publicada usa esta forma."""
    if document.get("schemaVersion") != 1:
        raise InvalidKnowledgeEntryError("El documento no es el esquema 1.")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise InvalidKnowledgeEntryError("El documento no trae entradas.")
    rows: list[ImportRow] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise InvalidKnowledgeEntryError("Una entrada del documento no es un objeto.")
        variations = raw.get("variations", [])
        if not isinstance(variations, list) or any(
            not isinstance(item, str) for item in variations
        ):
            raise InvalidKnowledgeEntryError("Cada variacion debe ser texto.")
        question = raw.get("question")
        view = raw.get("view")
        priority = raw.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise InvalidKnowledgeEntryError("La prioridad debe ser un entero.")
        rows.append(
            ImportRow(
                intent=str(raw.get("intent", "")),
                language=str(raw.get("language", "")),
                priority=priority,
                answer=str(raw.get("answer", "")),
                variations=tuple(variations),
                question=question if isinstance(question, str) else None,
                view=view if isinstance(view, str) else None,
            )
        )
    return tuple(rows)


def _imported(row: ImportRow) -> KnowledgeEntry:
    phrases = list(row.variations)
    question = row.question
    if question is not None:
        stripped = question.strip()
        if stripped != "" and stripped not in {item.strip() for item in phrases}:
            phrases = [question, *phrases]
    return knowledge_entry(
        entry_id=str(uuid4()),
        intent=row.intent,
        language=row.language,
        priority=row.priority,
        answer=row.answer,
        variations=phrases,
        view=row.view,
    )
