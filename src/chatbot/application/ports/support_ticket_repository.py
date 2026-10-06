"""Almacén de tickets. El identificador del jugador sale del token, no del cuerpo."""

from typing import Protocol

from chatbot.domain.support_ticket import SupportTicket


class SupportTicketRepository(Protocol):
    async def add(self, ticket: SupportTicket) -> None: ...

    async def list_all(self) -> tuple[SupportTicket, ...]: ...
