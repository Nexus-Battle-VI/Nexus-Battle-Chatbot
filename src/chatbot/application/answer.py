"""Responde una consulta con el diccionario (HU-47.2).

No inventa. Por debajo del umbral devuelve preguntas relacionadas. La vista,
si viene, elige la entrada de esa vista cuando existe.
"""

from dataclasses import dataclass

from chatbot.application.ports.intent_model import IntentModel, IntentModelFactory
from chatbot.application.ports.knowledge_entry_repository import KnowledgeEntryRepositoryPort
from chatbot.application.ports.model_trainer import ModelTrainer
from chatbot.application.ports.model_version_repository import ModelVersionRepository
from chatbot.domain.knowledge_entry import KnowledgeEntry
from chatbot.domain.normalize import normalize_question

CONFIDENCE_THRESHOLD = 0.55
_CACHE_LIMIT = 128


@dataclass(frozen=True)
class Answer:
    answered: bool
    intent: str | None
    language: str | None
    confidence: float
    answer: str | None
    kind: str
    suggestions: tuple[str, ...]
    view: str | None


def _label(entry: KnowledgeEntry) -> str:
    return f"{entry.language}:{entry.intent}"


def _split(label: str) -> tuple[str, str] | None:
    language, separator, intent = label.partition(":")
    if separator == "" or language not in {"es", "en"} or intent == "":
        return None
    return language, intent


def _choose(
    entries: tuple[KnowledgeEntry, ...], label: str, view: str | None
) -> KnowledgeEntry | None:
    parsed = _split(label)
    if parsed is None:
        return None
    language, intent = parsed
    matches = [entry for entry in entries if entry.language == language and entry.intent == intent]
    if view is not None:
        specific = [entry for entry in matches if entry.view == view]
        if specific:
            return max(specific, key=lambda entry: entry.priority)
    general = [entry for entry in matches if entry.view is None]
    pool = general or matches
    if not pool:
        return None
    return max(pool, key=lambda entry: entry.priority)


def _kind(entry: KnowledgeEntry, view: str | None) -> str:
    if view is not None and entry.view == view:
        return "contextual"
    if "\n" in entry.answer:
        return "steps"
    if "http://" in entry.answer or "https://" in entry.answer:
        return "enriched"
    return "direct"


class AnswerQuestion:
    def __init__(
        self,
        entries: KnowledgeEntryRepositoryPort,
        models: IntentModelFactory,
        versions: ModelVersionRepository | None = None,
        loader: ModelTrainer | None = None,
    ) -> None:
        self._entries = entries
        self._models = models
        self._versions = versions
        self._loader = loader
        self._fingerprint: tuple[object, ...] | None = None
        self._served_version: str | None = None
        self._model: IntentModel | None = None
        self._cache: dict[tuple[str | None, str, str | None], Answer] = {}

    async def execute(self, text: str, view: str | None) -> Answer:
        entries = await self._entries.list_all()
        fingerprint = tuple(
            (
                entry.id,
                entry.intent,
                entry.language,
                entry.priority,
                entry.view,
                entry.answer,
                entry.variations,
            )
            for entry in entries
        )
        active = None if self._versions is None else await self._versions.active()
        if active is None:
            if fingerprint != self._fingerprint:
                examples = tuple(
                    (_label(entry), normalize_question(variation))
                    for entry in entries
                    for variation in entry.variations
                )
                self._model = self._models.train(examples)
                self._fingerprint = fingerprint
                self._served_version = None
                self._cache.clear()
        else:
            if active.id != self._served_version:
                if self._loader is None:
                    raise RuntimeError("No hay cargador para la version activa.")
                self._model = self._loader.load(active.artifact)
                self._served_version = active.id
                self._cache.clear()
            if fingerprint != self._fingerprint:
                self._fingerprint = fingerprint
                self._cache.clear()

        normalized = normalize_question(text)
        key = (self._served_version, normalized, view)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        result = self._resolve(normalized, view, entries)
        if len(self._cache) >= _CACHE_LIMIT:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = result
        return result

    def _resolve(
        self,
        normalized: str,
        view: str | None,
        entries: tuple[KnowledgeEntry, ...],
    ) -> Answer:
        if normalized == "" or self._model is None:
            return Answer(False, None, None, 0.0, None, "direct", (), view)
        label, confidence, others = self._model.predict(normalized)
        chosen = None if label is None else _choose(entries, label, view)
        if chosen is None or confidence < CONFIDENCE_THRESHOLD:
            return Answer(
                False,
                None,
                None,
                confidence,
                None,
                "direct",
                _suggestions(entries, others, label),
                view,
            )
        return Answer(
            True,
            chosen.intent,
            chosen.language,
            confidence,
            chosen.answer,
            _kind(chosen, view),
            (),
            view,
        )


def _suggestions(
    entries: tuple[KnowledgeEntry, ...],
    others: tuple[str, ...],
    winner: str | None,
) -> tuple[str, ...]:
    questions: list[str] = []
    for label in others:
        if label == winner:
            continue
        entry = _choose(entries, label, None)
        if entry is None or not entry.variations:
            continue
        question = entry.variations[0]
        if question not in questions:
            questions.append(question)
        if len(questions) == 3:
            break
    return tuple(questions)
