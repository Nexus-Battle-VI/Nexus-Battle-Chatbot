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

    created, skipped, reinforced = await importer.execute(rows)
    assert skipped == 0
    assert reinforced == 0
    assert created == len(document["entries"])

    created_again, skipped_again, reinforced_again = await importer.execute(rows)
    assert created_again == 0
    assert reinforced_again == 0
    assert skipped_again == created

    stored = await repository.list_all()
    hero = next(
        entry for entry in stored if entry.intent == "producto_heroe" and entry.language == "es"
    )
    assert hero.variations[0] == "¿Qué héroes hay?"


def test_un_esquema_distinto_no_se_lee() -> None:
    with pytest.raises(InvalidKnowledgeEntryError, match="esquema"):
        rows_from_document({"schemaVersion": 2, "entries": []})


async def test_una_segunda_carga_suma_frases_y_conserva_la_respuesta() -> None:
    repository = InMemoryKnowledgeEntryRepository()
    importer = ImportKnowledgeEntries(repository)
    first = rows_from_document(
        {
            "schemaVersion": 1,
            "entries": [
                {
                    "intent": "regla_turno",
                    "language": "es",
                    "priority": 10,
                    "question": "¿Cómo funciona el turno?",
                    "variations": ["cuanto dura un turno"],
                    "answer": "El combate es por turnos.",
                }
            ],
        }
    )
    created, skipped, reinforced = await importer.execute(first)
    assert (created, skipped, reinforced) == (1, 0, 0)

    second = rows_from_document(
        {
            "schemaVersion": 1,
            "entries": [
                {
                    "intent": "regla_turno",
                    "language": "es",
                    "priority": 1,
                    "question": "¿Cómo funciona el turno?",
                    "variations": ["cuanto dura un turno", "en que orden juegan los equipos"],
                    "answer": "Esta respuesta no debe reemplazar la guardada.",
                }
            ],
        }
    )
    created, skipped, reinforced = await importer.execute(second)
    assert (created, skipped, reinforced) == (0, 0, 1)
    stored = (await repository.list_all())[0]
    assert stored.answer == "El combate es por turnos."
    assert stored.priority == 10
    assert "en que orden juegan los equipos" in stored.variations

    created, skipped, reinforced = await importer.execute(second)
    assert (created, skipped, reinforced) == (0, 1, 0)
