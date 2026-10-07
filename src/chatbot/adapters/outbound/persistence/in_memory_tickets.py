"""Tickets en memoria. Se pierden al reiniciar el proceso."""

from datetime import datetime

from chatbot.domain.support_ticket import SupportTicket


class InMemorySupportTicketRepository:
    def __init__(self) -> None:
        self._tickets: list[SupportTicket] = []

    async def add(self, ticket: SupportTicket) -> None:
        self._tickets.append(ticket)

    async def list_all(self) -> tuple[SupportTicket, ...]:
        return tuple(self._tickets)

    async def count_between(self, start: datetime, end: datetime) -> int:
        return sum(1 for ticket in self._tickets if start <= ticket.created_at <= end)
