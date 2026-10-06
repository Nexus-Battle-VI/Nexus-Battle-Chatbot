"""Agregados del panel de uso (HU-52).

Cuenta lo ya guardado. No inventa una duración, una intención ni una
valoración que no estén en el turno. Las palabras de función se descartan
porque no son tema de consulta.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from chatbot.domain.normalize import normalize_question

PANEL_LIMIT = 10
MAX_PERIOD_DAYS = 366
_FUNCTION_WORDS = frozenset(
    {
        "los",
        "las",
        "una",
        "unos",
        "unas",
        "del",
        "que",
        "por",
        "para",
        "con",
        "sin",
        "sus",
        "mis",
        "tus",
        "les",
        "son",
        "como",
        "the",
        "and",
        "for",
        "redactado",
    }
)


@dataclass(frozen=True)
class ObservedQuery:
    text: str
    answered: bool
    intent: str | None
    useful: bool | None
    duration_ms: int | None
    created_at: datetime


@dataclass(frozen=True)
class CountedText:
    text: str
    count: int


@dataclass(frozen=True)
class CountedTopic:
    intent: str | None
    count: int


@dataclass(frozen=True)
class TrendPoint:
    day: date
    queries: int
    resolved: int


@dataclass(frozen=True)
class UsageReport:
    conversations_started: int
    frequent_questions: tuple[CountedText, ...]
    topics: tuple[CountedTopic, ...]
    resolution_rate: float | None
    average_response_ms: float | None
    satisfaction: float | None
    escalations: int
    keywords: tuple[CountedText, ...]
    trend: tuple[TrendPoint, ...]


def summarize(
    queries: tuple[ObservedQuery, ...],
    conversations_started: int,
    escalations: int,
    start: datetime,
    end: datetime,
) -> UsageReport:
    questions: Counter[str] = Counter()
    topics: Counter[str | None] = Counter()
    keywords: Counter[str] = Counter()
    per_day: Counter[date] = Counter()
    resolved_day: Counter[date] = Counter()
    useful = 0
    not_useful = 0
    durations: list[int] = []
    resolved = 0
    for query in queries:
        day = query.created_at.astimezone(UTC).date()
        per_day[day] += 1
        if query.answered:
            resolved += 1
            resolved_day[day] += 1
        if query.useful is True:
            useful += 1
        elif query.useful is False:
            not_useful += 1
        if query.duration_ms is not None:
            durations.append(query.duration_ms)
        normalized = normalize_question(query.text)
        if normalized != "":
            questions[normalized] += 1
            for token in normalized.split(" "):
                if len(token) < 3 or token in _FUNCTION_WORDS:
                    continue
                keywords[token] += 1
        topics[query.intent] += 1
    total = len(queries)
    rated = useful + not_useful
    return UsageReport(
        conversations_started,
        _texts(questions),
        _topics(topics),
        None if total == 0 else resolved / total,
        None if len(durations) == 0 else sum(durations) / len(durations),
        None if rated == 0 else useful / rated,
        escalations,
        _texts(keywords),
        _trend(start, end, per_day, resolved_day),
    )


def _texts(counts: Counter[str]) -> tuple[CountedText, ...]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(CountedText(text, count) for text, count in ordered[:PANEL_LIMIT])


def _topics(counts: Counter[str | None]) -> tuple[CountedTopic, ...]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0] or ""))
    return tuple(CountedTopic(intent, count) for intent, count in ordered[:PANEL_LIMIT])


def _trend(
    start: datetime,
    end: datetime,
    per_day: Counter[date],
    resolved_day: Counter[date],
) -> tuple[TrendPoint, ...]:
    first = start.astimezone(UTC).date()
    last = end.astimezone(UTC).date()
    points: list[TrendPoint] = []
    day = first
    while day <= last:
        points.append(TrendPoint(day, per_day[day], resolved_day[day]))
        day += timedelta(days=1)
    return tuple(points)
