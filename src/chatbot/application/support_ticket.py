"""Abre un ticket cuando la consulta no se resolvió (HU-49)."""

from uuid import uuid4

from chatbot.application.ports.clock import ClockPort
from chatbot.application.ports.support_ticket_repository import SupportTicketRepository
from chatbot.domain.support_ticket import SupportTicket


class OpenSupportTicket:
    def __init__(self, tickets: SupportTicketRepository, clock: ClockPort) -> None:
        self._tickets = tickets
        self._clock = clock

    async def execute(self, actor: str, question: str, view: str | None) -> SupportTicket:
        ticket = SupportTicket(
            id=str(uuid4()),
            actor=actor,
            question=question,
            view=view,
            created_at=self._clock.now(),
        )
        await self._tickets.add(ticket)
        return ticket


class ListSupportTickets:
    def __init__(self, tickets: SupportTicketRepository) -> None:
        self._tickets = tickets

    async def execute(self) -> tuple[SupportTicket, ...]:
        return await self._tickets.list_all()
