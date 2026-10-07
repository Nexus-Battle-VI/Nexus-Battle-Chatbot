"""Rutas de administracion del diccionario (HU-53.1).

Nacen protegidas. Exigen ADMINISTRATOR. El sujeto sale del token, nunca del cuerpo.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from chatbot.adapters.inbound.http.auth.guards import require_roles
from chatbot.application.knowledge import (
    CreateKnowledgeEntry,
    DeleteKnowledgeEntry,
    ImportKnowledgeEntries,
    ImportRow,
    KnowledgeEntryNotFoundError,
    ListKnowledgeEntries,
    UpdateKnowledgeEntry,
    export_document,
)
from chatbot.application.ports.token_verifier import Role
from chatbot.domain.errors import InvalidKnowledgeEntryError
from chatbot.domain.knowledge_entry import KnowledgeEntry

_ADMIN = [Depends(require_roles(Role.ADMINISTRATOR))]


class KnowledgeEntryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    language: str
    priority: int
    answer: str
    variations: list[str]
    view: str | None = None


class ImportEntryBody(BaseModel):
    """Acepta la semilla publicada: ignora liveData y assistedAction."""

    model_config = ConfigDict(extra="ignore")

    intent: str
    language: str
    priority: int
    answer: str
    variations: list[str] = []
    question: str | None = None
    view: str | None = None


class ImportDocumentBody(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_version: int = Field(alias="schemaVersion")
    entries: list[ImportEntryBody]


def _view(entry: KnowledgeEntry) -> dict[str, object]:
    return {
        "id": entry.id,
        "intent": entry.intent,
        "language": entry.language,
        "priority": entry.priority,
        "answer": entry.answer,
        "variations": list(entry.variations),
        "view": entry.view,
    }


def _invalid(error: InvalidKnowledgeEntryError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(error))


def knowledge_router(
    *,
    create: CreateKnowledgeEntry,
    update: UpdateKnowledgeEntry,
    delete: DeleteKnowledgeEntry,
    list_entries: ListKnowledgeEntries,
    import_entries: ImportKnowledgeEntries,
) -> APIRouter:
    router = APIRouter(prefix="/admin/knowledge", tags=["knowledge"])

    @router.get("", dependencies=_ADMIN)
    async def list_knowledge() -> list[dict[str, object]]:
        entries = await list_entries.execute()
        return [_view(entry) for entry in entries]

    @router.get("/export", dependencies=_ADMIN)
    async def export_knowledge() -> dict[str, object]:
        return export_document(await list_entries.execute())

    @router.post("/import", dependencies=_ADMIN)
    async def import_knowledge(body: ImportDocumentBody) -> dict[str, int]:
        if body.schema_version != 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El documento no es el esquema 1.")
        rows = tuple(
            ImportRow(
                intent=item.intent,
                language=item.language,
                priority=item.priority,
                answer=item.answer,
                variations=tuple(item.variations),
                question=item.question,
                view=item.view,
            )
            for item in body.entries
        )
        try:
            created, skipped = await import_entries.execute(rows)
        except InvalidKnowledgeEntryError as error:
            raise _invalid(error) from error
        return {"created": created, "skipped": skipped}

    @router.post("", status_code=status.HTTP_201_CREATED, dependencies=_ADMIN)
    async def create_knowledge(body: KnowledgeEntryBody) -> dict[str, object]:
        try:
            entry = await create.execute(
                intent=body.intent,
                language=body.language,
                priority=body.priority,
                answer=body.answer,
                variations=body.variations,
                view=body.view,
            )
        except InvalidKnowledgeEntryError as error:
            raise _invalid(error) from error
        return _view(entry)

    @router.put("/{entry_id}", dependencies=_ADMIN)
    async def update_knowledge(entry_id: str, body: KnowledgeEntryBody) -> dict[str, object]:
        try:
            entry = await update.execute(
                entry_id,
                intent=body.intent,
                language=body.language,
                priority=body.priority,
                answer=body.answer,
                variations=body.variations,
                view=body.view,
            )
        except InvalidKnowledgeEntryError as error:
            raise _invalid(error) from error
        except KnowledgeEntryNotFoundError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        return _view(entry)

    @router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_ADMIN)
    async def delete_knowledge(entry_id: str) -> None:
        try:
            await delete.execute(entry_id)
        except KnowledgeEntryNotFoundError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    return router
