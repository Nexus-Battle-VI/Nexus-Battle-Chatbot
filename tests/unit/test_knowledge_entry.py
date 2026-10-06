"""Diccionario: forma del dominio y semilla publicada."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from chatbot.domain.errors import InvalidKnowledgeEntryError
from chatbot.domain.knowledge_entry import knowledge_entry
from chatbot.domain.live_query import LIVE_SOURCES

_SEED = Path(__file__).resolve().parents[2] / "docs" / "diccionario" / "semilla-v1.json"


def test_acepta_una_entrada_completa() -> None:
    entry = knowledge_entry(
        entry_id=str(uuid4()),
        intent="regla_turno",
        language="es",
        priority=10,
        answer="El combate es por turnos.",
        variations=["como funciona el turno", "  cuanto dura un turno  "],
    )
    assert entry.variations == ("como funciona el turno", "cuanto dura un turno")


@pytest.mark.parametrize(
    ("kwargs", "fragmento"),
    [
        ({"intent": "Regla"}, "intencion"),
        ({"language": "fr"}, "idioma"),
        ({"priority": True}, "prioridad"),
        ({"answer": "   "}, "respuesta"),
        ({"variations": []}, "variacion"),
        ({"variations": ["hola", "hola"]}, "repite"),
        ({"entry_id": "no-es-uuid"}, "UUID"),
    ],
)
def test_rechaza_una_entrada_invalida(kwargs: dict[str, object], fragmento: str) -> None:
    base: dict[str, object] = {
        "entry_id": str(uuid4()),
        "intent": "regla_turno",
        "language": "es",
        "priority": 1,
        "answer": "texto",
        "variations": ["pregunta"],
    }
    base.update(kwargs)
    with pytest.raises(InvalidKnowledgeEntryError, match=fragmento):
        knowledge_entry(**base)  # type: ignore[arg-type]


def test_la_semilla_es_un_conjunto_valido_de_entradas() -> None:
    document = json.loads(_SEED.read_text(encoding="utf-8"))
    seen: set[tuple[str, str]] = set()
    for raw in document["entries"]:
        phrases = [raw["question"], *raw["variations"]]
        entry = knowledge_entry(
            entry_id=str(uuid4()),
            intent=raw["intent"],
            language=raw["language"],
            priority=raw["priority"],
            answer=raw["answer"],
            variations=phrases,
        )
        assert raw["liveData"] == LIVE_SOURCES.get(raw["intent"])
        key = (entry.intent, entry.language)
        assert key not in seen
        seen.add(key)
    assert len(seen) == 50 + len(LIVE_SOURCES) * 2
