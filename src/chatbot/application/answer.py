"""Responde una consulta con el diccionario (HU-47.2).

No inventa. Por debajo del umbral devuelve preguntas relacionadas. La vista,
si viene, elige la entrada de esa vista cuando existe.
"""

from dataclasses import dataclass, replace

from chatbot.application.ports.intent_model import IntentModel, IntentModelFactory
from chatbot.application.ports.knowledge_entry_repository import KnowledgeEntryRepositoryPort
from chatbot.application.ports.model_trainer import ModelTrainer
from chatbot.application.ports.model_version_repository import (
    ModelVersion,
    ModelVersionRepository,
)
from chatbot.application.ports.player_data import PlayerDataPort
from chatbot.domain.assisted_action import assisted_action
from chatbot.domain.experiment import sees_candidate
from chatbot.domain.knowledge_entry import KnowledgeEntry
from chatbot.domain.live_query import SIGN_IN, UNAVAILABLE, live_source
from chatbot.domain.live_summary import (
    summarize_auctions,
    summarize_inventory,
    summarize_missions,
    summarize_notifications,
    summarize_transactions,
)
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
    model_version: str | None = None
    assisted_action: tuple[str, str] | None = None


_SUMMARIES = {
    "inventory": summarize_inventory,
    "missions": summarize_missions,
    "auction": summarize_auctions,
    "notifications": summarize_notifications,
    "transactions": summarize_transactions,
}


def _summary(source: str, payload: dict[str, object]) -> str | None:
    summarize = _SUMMARIES.get(source)
    if summarize is None:
        return None
    return summarize(payload)


def _fingerprint(entries: tuple[KnowledgeEntry, ...]) -> tuple[object, ...]:
    return tuple(
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
        candidate_percent: int = 0,
        *,
        player_data: PlayerDataPort | None = None,
    ) -> None:
        self._entries = entries
        self._models = models
        self._versions = versions
        self._loader = loader
        self._percent = candidate_percent
        self._player_data = player_data
        self._fingerprint: tuple[object, ...] | None = None
        self._served_version: str | None = None
        self._model: IntentModel | None = None
        self._loaded: dict[str, IntentModel] = {}
        self._cache: dict[tuple[str | None, str, str | None], Answer] = {}

    async def execute(
        self,
        text: str,
        view: str | None,
        actor: str | None = None,
        *,
        access_token: str | None = None,
    ) -> Answer:
        entries = await self._entries.list_all()
        fingerprint = _fingerprint(entries)
        chosen = await self._choose_version(actor)
        if chosen is None:
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
            if chosen.id not in self._loaded:
                if self._loader is None:
                    raise RuntimeError("No hay cargador para la version activa.")
                self._loaded[chosen.id] = self._loader.load(chosen.artifact)
            self._model = self._loaded[chosen.id]
            if chosen.id != self._served_version or fingerprint != self._fingerprint:
                self._served_version = chosen.id
                self._fingerprint = fingerprint
                self._cache.clear()

        normalized = normalize_question(text)
        version_id = None if chosen is None else chosen.id
        source = None
        label = None
        if self._model is not None and normalized != "":
            label = self._model.predict(normalized)[0]
            source = live_source(label)
        if source is not None:
            result = await self._live(source, access_token, label)
            result = replace(
                result,
                model_version=version_id,
                assisted_action=assisted_action(label),
            )
            await self._note(version_id)
            return result
        key = (version_id, normalized, view)
        cached = self._cache.get(key)
        if cached is not None:
            await self._note(version_id)
            return cached

        result = replace(
            self._resolve(normalized, view, entries),
            model_version=version_id,
            assisted_action=assisted_action(label),
        )
        if len(self._cache) >= _CACHE_LIMIT:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = result
        await self._note(version_id)
        return result

    async def _choose_version(self, actor: str | None) -> ModelVersion | None:
        if self._versions is None:
            return None
        active = await self._versions.active()
        if active is None:
            return None
        if self._percent <= 0 or actor is None:
            return active
        candidate = await self._versions.experiment_candidate()
        if candidate is not None and sees_candidate(actor, self._percent):
            return candidate
        return active

    async def _note(self, version_id: str | None) -> None:
        if version_id is None or self._versions is None:
            return
        await self._versions.record_answer(version_id)

    async def _live(self, source: str, access_token: str | None, label: str | None) -> Answer:
        language, _, intent = (label or "").partition(":")
        blank = Answer(True, intent or None, language or None, 1.0, UNAVAILABLE, "direct", (), None)
        if access_token is None:
            return Answer(True, intent or None, language or None, 1.0, SIGN_IN, "direct", (), None)
        if self._player_data is None or source == "tournament":
            return blank
        payload = await self._player_data.fetch(source, access_token)
        if payload is None:
            return blank
        summary = _summary(source, payload)
        if summary is None:
            return blank
        return Answer(True, intent or None, language or None, 1.0, summary, "direct", (), None)

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
