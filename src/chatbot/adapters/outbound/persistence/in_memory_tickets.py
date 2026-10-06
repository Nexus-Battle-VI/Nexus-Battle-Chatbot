"""Tickets en memoria. Se pierden al reiniciar el proceso."""

from chatbot.domain.support_ticket import SupportTicket


class InMemorySupportTicketRepository:
    def __init__(self) -> None:
        self._tickets: list[SupportTicket] = []

    async def add(self, ticket: SupportTicket) -> None:
        self._tickets.append(ticket)

    async def list_all(self) -> tuple[SupportTicket, ...]:
        return tuple(self._tickets)
