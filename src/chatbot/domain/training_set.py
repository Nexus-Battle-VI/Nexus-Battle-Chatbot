"""Reglas del conjunto y de la promoción (HU-54.2).

El dominio no entrena: solo decide qué texto entra y si una candidata puede
sustituir a la versión vigente. Los números salen del contrato
`hu-54-model-versions-v1`.
"""

from dataclasses import dataclass

from chatbot.domain.knowledge_entry import KnowledgeEntry
from chatbot.domain.normalize import normalize_question

MINIMUM_ACCURACY = 0.80
_LANGUAGES = frozenset({"es", "en"})


@dataclass(frozen=True)
class ConversationTurn:
    """Una conversación ya guardada. `useful` vacío significa que nadie la valoró."""

    text: str
    language: str
    intent: str | None
    useful: bool | None
    deleted: bool


@dataclass(frozen=True)
class ValidationMetrics:
    accuracy: float
    macro_f1: float
    per_intent_f1: tuple[tuple[str, float], ...]
    confusion: tuple[tuple[str, str, int], ...]


def conversation_example(turn: ConversationTurn) -> tuple[str, str] | None:
    """Ejemplo de entrenamiento, o nada si la conversación no puede usarse.

    Útil y con intención: entra. No útil: está revisada y no se suma como
    ejemplo de esa intención. Sin valoración, borrada o sin intención: no entra.
    """
    if turn.deleted or turn.useful is not True:
        return None
    if turn.intent is None or turn.intent == "" or turn.language not in _LANGUAGES:
        return None
    text = normalize_question(turn.text)
    if text == "":
        return None
    return f"{turn.language}:{turn.intent}", text


def dictionary_examples(entries: tuple[KnowledgeEntry, ...]) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for entry in entries:
        label = f"{entry.language}:{entry.intent}"
        for variation in entry.variations:
            text = normalize_question(variation)
            if text != "":
                rows.append((label, text))
    return tuple(rows)


def split_examples(
    examples: tuple[tuple[str, str], ...],
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...], tuple[str, ...]]:
    """80/20 por etiqueta. Una clase con un solo ejemplo se queda en el entrenamiento."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for label, text in sorted(examples):
        grouped.setdefault(label, []).append((label, text))
    train: list[tuple[str, str]] = []
    validation: list[tuple[str, str]] = []
    singles: list[str] = []
    for label in sorted(grouped):
        rows = grouped[label]
        if len(rows) < 2:
            train.extend(rows)
            singles.append(label)
            continue
        holdout = min(max(1, round(len(rows) * 0.2)), len(rows) - 1)
        validation.extend(rows[:holdout])
        train.extend(rows[holdout:])
    return tuple(train), tuple(validation), tuple(singles)


def validation_metrics(expected: tuple[str, ...], predicted: tuple[str, ...]) -> ValidationMetrics:
    if len(expected) == 0:
        return ValidationMetrics(0.0, 0.0, (), ())
    pairs = tuple(zip(expected, predicted, strict=True))
    accuracy = sum(1 for actual, guess in pairs if actual == guess) / len(pairs)
    scores = tuple((label, _f1(label, pairs)) for label in sorted(set(expected)))
    macro = sum(score for _label, score in scores) / len(scores)
    counts: dict[tuple[str, str], int] = {}
    for actual, guess in pairs:
        counts[(actual, guess)] = counts.get((actual, guess), 0) + 1
    confusion = tuple((actual, guess, count) for (actual, guess), count in sorted(counts.items()))
    return ValidationMetrics(accuracy, macro, scores, confusion)


def should_promote(metrics: ValidationMetrics, active_macro_f1: float | None) -> bool:
    """La primera activa exige 0,80. Las siguientes, además, no bajan el F1 macro."""
    if metrics.accuracy < MINIMUM_ACCURACY:
        return False
    if active_macro_f1 is None:
        return True
    return metrics.macro_f1 >= active_macro_f1


def _f1(label: str, pairs: tuple[tuple[str, str], ...]) -> float:
    true_positive = sum(1 for actual, guess in pairs if actual == label and guess == label)
    false_positive = sum(1 for actual, guess in pairs if actual != label and guess == label)
    false_negative = sum(1 for actual, guess in pairs if actual == label and guess != label)
    if true_positive == 0:
        return 0.0
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    return 2 * precision * recall / (precision + recall)
