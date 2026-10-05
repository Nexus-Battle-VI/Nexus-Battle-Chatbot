"""Diccionario en la base propia del chatbot."""

import json

from psycopg_pool import AsyncConnectionPool

from chatbot.domain.errors import InvalidKnowledgeEntryError
from chatbot.domain.knowledge_entry import KnowledgeEntry, knowledge_entry


def _variations(raw: object) -> list[str]:
    parsed: object = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, list):
        raise InvalidKnowledgeEntryError("Las variaciones guardadas no son texto.")
    texts: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise InvalidKnowledgeEntryError("Las variaciones guardadas no son texto.")
        texts.append(item)
    return texts


def _entry(row: tuple[object, ...]) -> KnowledgeEntry:
    priority = row[3]
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise InvalidKnowledgeEntryError("La prioridad guardada no es un entero.")
    return knowledge_entry(
        entry_id=str(row[0]),
        intent=str(row[1]),
        language=str(row[2]),
        priority=priority,
        answer=str(row[4]),
        variations=_variations(row[5]),
    )


class PostgresKnowledgeEntryRepository:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def add(self, entry: KnowledgeEntry) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "insert into knowledge_entries"
                " (id, intent, language, priority, answer, variations)"
                " values (%s, %s, %s, %s, %s, %s::jsonb)",
                (
                    entry.id,
                    entry.intent,
                    entry.language,
                    entry.priority,
                    entry.answer,
                    json.dumps(list(entry.variations)),
                ),
            )

    async def save(self, entry: KnowledgeEntry) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "update knowledge_entries"
                " set intent = %s, language = %s, priority = %s,"
                " answer = %s, variations = %s::jsonb"
                " where id = %s",
                (
                    entry.intent,
                    entry.language,
                    entry.priority,
                    entry.answer,
                    json.dumps(list(entry.variations)),
                    entry.id,
                ),
            )
            return cursor.rowcount == 1

    async def remove(self, entry_id: str) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "delete from knowledge_entries where id = %s",
                (entry_id,),
            )
            return cursor.rowcount == 1

    async def get(self, entry_id: str) -> KnowledgeEntry | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select id::text, intent, language, priority, answer, variations"
                " from knowledge_entries where id = %s",
                (entry_id,),
            )
            row = await cursor.fetchone()
        return None if row is None else _entry(row)

    async def list_all(self) -> tuple[KnowledgeEntry, ...]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select id::text, intent, language, priority, answer, variations"
                " from knowledge_entries"
                " order by intent, language, priority desc, id"
            )
            rows = await cursor.fetchall()
        return tuple(_entry(row) for row in rows)
