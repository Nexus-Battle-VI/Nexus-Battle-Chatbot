"""Versiones del modelo en la base propia del chatbot."""

import json
from datetime import datetime

from psycopg_pool import AsyncConnectionPool

from chatbot.application.ports.model_version_repository import ModelVersion
from chatbot.domain.training_set import ValidationMetrics


class PostgresModelVersionRepository:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def active(self) -> ModelVersion | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select id, state, accuracy, macro_f1, report, artifact, created_at"
                " from model_versions where state = 'ACTIVE'"
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _version(row)

    async def add_candidate(self, version: ModelVersion) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "insert into model_versions"
                " (id, state, accuracy, macro_f1, report, artifact, created_at)"
                " values (%s, 'CANDIDATE', %s, %s, %s::jsonb, %s, %s)",
                (
                    version.id,
                    version.accuracy,
                    version.macro_f1,
                    json.dumps(_report(version)),
                    version.artifact,
                    version.created_at,
                ),
            )

    async def promote(self, version_id: str) -> bool:
        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute(
                "update model_versions set state = 'CANDIDATE' where state = 'ACTIVE'"
            )
            cursor = await connection.execute(
                "update model_versions set state = 'ACTIVE' where id = %s and state = 'CANDIDATE'",
                (version_id,),
            )
            return cursor.rowcount == 1

    async def try_acquire(self, now: datetime, until: datetime) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "update model_training_lease set until = %s"
                " where id = 1 and until <= %s returning id",
                (until, now),
            )
            row = await cursor.fetchone()
        return row is not None

    async def release(self) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "update model_training_lease set until = '-infinity' where id = 1"
            )


def _report(version: ModelVersion) -> dict[str, object]:
    return {
        "accuracy": version.metrics.accuracy,
        "macroF1": version.metrics.macro_f1,
        "perIntentF1": dict(version.metrics.per_intent_f1),
        "confusion": [
            {"actual": actual, "predicted": predicted, "count": count}
            for actual, predicted, count in version.metrics.confusion
        ],
        "singleExampleLabels": list(version.single_example_labels),
    }


def _version(row: tuple[object, ...]) -> ModelVersion:
    report = _object(row[4])
    created = row[6]
    if not isinstance(created, datetime):
        raise TypeError("La fecha de la version no es una fecha.")
    accuracy = _number(row[2])
    macro = _number(row[3])
    return ModelVersion(
        id=str(row[0]),
        state=str(row[1]),
        accuracy=accuracy,
        macro_f1=macro,
        metrics=_metrics(report),
        single_example_labels=_labels(report.get("singleExampleLabels")),
        artifact=bytes(row[5]) if isinstance(row[5], bytes | memoryview) else b"",
        created_at=created,
    )


def _object(raw: object) -> dict[str, object]:
    parsed: object = json.loads(raw) if isinstance(raw, str | bytes) else raw
    if not isinstance(parsed, dict):
        return {}
    return {str(key): value for key, value in parsed.items()}


def _metrics(report: dict[str, object]) -> ValidationMetrics:
    scores: list[tuple[str, float]] = []
    raw_scores = report.get("perIntentF1")
    if isinstance(raw_scores, dict):
        for label, score in raw_scores.items():
            if isinstance(score, int | float) and not isinstance(score, bool):
                scores.append((str(label), float(score)))
    confusion: list[tuple[str, str, int]] = []
    raw_confusion = report.get("confusion")
    if isinstance(raw_confusion, list):
        for item in raw_confusion:
            if not isinstance(item, dict):
                continue
            count = item.get("count")
            if isinstance(count, int) and not isinstance(count, bool):
                confusion.append((str(item.get("actual")), str(item.get("predicted")), count))
    return ValidationMetrics(
        _number(report.get("accuracy")),
        _number(report.get("macroF1")),
        tuple(scores),
        tuple(confusion),
    )


def _number(raw: object) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return 0.0
    return float(raw)


def _labels(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw if isinstance(item, str))
