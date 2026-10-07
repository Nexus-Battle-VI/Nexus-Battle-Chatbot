"""Entrada del diccionario de intenciones (HU-53.1).

El dominio no sabe de HTTP ni de PostgreSQL. Solo exige la forma que el
contrato `hu-53-knowledge-base-v1` fija: intencion, idioma, prioridad,
respuesta y al menos una variacion de pregunta.
"""

import re
from dataclasses import dataclass
from uuid import UUID

from chatbot.domain.errors import InvalidKnowledgeEntryError

_INTENT = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_LANGUAGES = frozenset({"es", "en"})
_MAX_ANSWER = 8_000
_MAX_VARIATIONS = 30
_MAX_VARIATION = 500
_VIEW = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


@dataclass(frozen=True)
class KnowledgeEntry:
    id: str
    intent: str
    language: str
    priority: int
    answer: str
    variations: tuple[str, ...]
    view: str | None = None


def question_view(view: str | None) -> str | None:
    """Vista de la consulta. Vacia significa que no hay vista."""
    if view is None:
        return None
    if not isinstance(view, str) or _VIEW.fullmatch(view) is None:
        raise InvalidKnowledgeEntryError(
            "La vista debe ser minusculas, numeros, guion o guion bajo."
        )
    return view


def knowledge_entry(
    *,
    entry_id: str,
    intent: str,
    language: str,
    priority: int,
    answer: str,
    variations: tuple[str, ...] | list[str],
    view: str | None = None,
) -> KnowledgeEntry:
    """Valida y congela una entrada. No recorta en silencio un dato invalido."""
    try:
        parsed_id = str(UUID(entry_id))
    except (ValueError, AttributeError, TypeError) as error:
        raise InvalidKnowledgeEntryError("El identificador de la entrada no es un UUID.") from error

    if not isinstance(intent, str) or _INTENT.fullmatch(intent) is None:
        raise InvalidKnowledgeEntryError(
            "La intencion debe ser minusculas, numeros o guion bajo, y empezar por una letra."
        )
    if language not in _LANGUAGES:
        raise InvalidKnowledgeEntryError("El idioma debe ser es o en.")
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise InvalidKnowledgeEntryError("La prioridad debe ser un entero.")

    parsed_view = question_view(view)

    if not isinstance(answer, str) or answer.strip() == "":
        raise InvalidKnowledgeEntryError("La respuesta no puede estar vacia.")
    if len(answer) > _MAX_ANSWER:
        raise InvalidKnowledgeEntryError("La respuesta supera el largo permitido.")

    if not isinstance(variations, (tuple, list)) or len(variations) == 0:
        raise InvalidKnowledgeEntryError("La entrada necesita al menos una variacion de pregunta.")
    if len(variations) > _MAX_VARIATIONS:
        raise InvalidKnowledgeEntryError("La entrada tiene demasiadas variaciones.")

    cleaned: list[str] = []
    for variation in variations:
        if not isinstance(variation, str):
            raise InvalidKnowledgeEntryError("Cada variacion debe ser texto.")
        text = variation.strip()
        if text == "" or len(text) > _MAX_VARIATION:
            raise InvalidKnowledgeEntryError(
                "Una variacion esta vacia o supera el largo permitido."
            )
        if text in cleaned:
            raise InvalidKnowledgeEntryError("La entrada repite una variacion.")
        cleaned.append(text)

    return KnowledgeEntry(
        id=parsed_id,
        intent=intent,
        language=language,
        priority=priority,
        answer=answer,
        variations=tuple(cleaned),
        view=parsed_view,
    )
