"""La semilla publicada entra al diccionario una sola vez."""

import json
from pathlib import Path

import pytest

from chatbot.adapters.outbound.persistence.in_memory_knowledge import (
    InMemoryKnowledgeEntryRepository,
)
from chatbot.application.knowledge import ImportKnowledgeEntries, rows_from_document
from chatbot.domain.errors import InvalidKnowledgeEntryError

pytestmark = pytest.mark.anyio

_SEED = Path(__file__).resolve().parents[2] / "docs" / "diccionario" / "semilla-v1.json"


async def test_la_semilla_publicada_entra_una_sola_vez() -> None:
    document = json.loads(_SEED.read_text(encoding="utf-8"))
    rows = rows_from_document(document)
    repository = InMemoryKnowledgeEntryRepository()
    importer = ImportKnowledgeEntries(repository)

    created, skipped = await importer.execute(rows)
    assert skipped == 0
    assert created == len(document["entries"])

    created_again, skipped_again = await importer.execute(rows)
    assert created_again == 0
    assert skipped_again == created

    stored = await repository.list_all()
    hero = next(
        entry for entry in stored if entry.intent == "producto_heroe" and entry.language == "es"
    )
    assert hero.variations[0] == "¿Qué héroes hay?"


def test_un_esquema_distinto_no_se_lee() -> None:
    with pytest.raises(InvalidKnowledgeEntryError, match="esquema"):
        rows_from_document({"schemaVersion": 2, "entries": []})
