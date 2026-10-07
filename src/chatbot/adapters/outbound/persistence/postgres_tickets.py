"""Tickets en la base propia del chatbot."""

from datetime import datetime

from psycopg_pool import AsyncConnectionPool

from chatbot.domain.support_ticket import SupportTicket


class PostgresSupportTicketRepository:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def add(self, ticket: SupportTicket) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "insert into support_tickets (id, actor, question, view, created_at)"
                " values (%s, %s, %s, %s, %s)",
                (ticket.id, ticket.actor, ticket.question, ticket.view, ticket.created_at),
            )

    async def list_all(self) -> tuple[SupportTicket, ...]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select id, actor, question, view, created_at"
                " from support_tickets order by created_at"
            )
            rows = await cursor.fetchall()
        return tuple(_ticket(row) for row in rows)

    async def count_between(self, start: datetime, end: datetime) -> int:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "select count(*) from support_tickets where created_at >= %s and created_at <= %s",
                (start, end),
            )
            row = await cursor.fetchone()
        return 0 if row is None else int(row[0])


def _ticket(row: tuple[object, ...]) -> SupportTicket:
    created = row[4]
    if not isinstance(created, datetime):
        raise TypeError("La fecha del ticket no es una fecha.")
    return SupportTicket(
        id=str(row[0]),
        actor=str(row[1]),
        question=str(row[2]),
        view=None if row[3] is None else str(row[3]),
        created_at=created,
    )
