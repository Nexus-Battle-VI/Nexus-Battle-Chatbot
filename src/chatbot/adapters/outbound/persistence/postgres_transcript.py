"""Historial en la base propia del chatbot. Pregunta y respuesta van cifradas."""

from datetime import datetime

from psycopg_pool import AsyncConnectionPool

from chatbot.application.ports.transcript_repository import StoredTurn


class PostgresTranscriptRepository:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def add(self, actor: str, turn: StoredTurn) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "insert into conversation_turns ("
                " id, actor, question, answer, language, intent, model_version,"
                " useful, created_at) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    turn.id,
                    actor,
                    turn.question,
                    turn.answer,
                    turn.language,
                    turn.intent,
                    turn.model_version,
                    turn.useful,
                    turn.created_at,
                ),
            )

    async def list_active(self, actor: str) -> tuple[StoredTurn, ...]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select id, question, answer, language, intent, model_version, useful, created_at"
                " from conversation_turns"
                " where actor = %s and deleted = false"
                " order by created_at, id",
                (actor,),
            )
            rows = await cursor.fetchall()
        return tuple(_turn(row) for row in rows)

    async def get(self, actor: str, turn_id: str) -> StoredTurn | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select id, question, answer, language, intent, model_version, useful, created_at"
                " from conversation_turns"
                " where actor = %s and id = %s and deleted = false",
                (actor, turn_id),
            )
            row = await cursor.fetchone()
        return None if row is None else _turn(row)

    async def clear(self, actor: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "update conversation_turns set deleted = true where actor = %s",
                (actor,),
            )

    async def set_useful(self, actor: str, turn_id: str, useful: bool) -> StoredTurn | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "update conversation_turns set useful = %s"
                " where actor = %s and id = %s and deleted = false"
                " returning id, question, answer, language, intent,"
                " model_version, useful, created_at",
                (useful, actor, turn_id),
            )
            row = await cursor.fetchone()
        return None if row is None else _turn(row)

    async def list_rated(self) -> tuple[StoredTurn, ...]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select id, question, answer, language, intent, model_version, useful, created_at"
                " from conversation_turns"
                " where deleted = false and useful is not null"
                " order by created_at, id"
            )
            rows = await cursor.fetchall()
        return tuple(_turn(row) for row in rows)

    async def remember_visitor(self, session_id: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "insert into visitor_sessions (id) values (%s) on conflict do nothing",
                (session_id,),
            )

    async def visitor_known(self, session_id: str) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select 1 from visitor_sessions where id = %s",
                (session_id,),
            )
            return await cursor.fetchone() is not None

    async def show_time(self, actor: str) -> bool | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select show_time from chat_preferences where actor = %s",
                (actor,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return bool(row[0])

    async def set_show_time(self, actor: str, show_time: bool) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "insert into chat_preferences (actor, show_time) values (%s, %s)"
                " on conflict (actor) do update set show_time = excluded.show_time",
                (actor, show_time),
            )


def _turn(row: tuple[object, ...]) -> StoredTurn:
    created = row[7]
    if not isinstance(created, datetime):
        raise TypeError("La fecha del turno no es una fecha.")
    useful = row[6]
    return StoredTurn(
        id=str(row[0]),
        question=str(row[1]),
        answer=None if row[2] is None else str(row[2]),
        language=None if row[3] is None else str(row[3]),
        intent=None if row[4] is None else str(row[4]),
        model_version=None if row[5] is None else str(row[5]),
        useful=None if useful is None else bool(useful),
        created_at=created,
    )
