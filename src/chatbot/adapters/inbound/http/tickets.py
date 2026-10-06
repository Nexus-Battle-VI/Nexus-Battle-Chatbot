"""Consulta de tickets de escalamiento (HU-49). Exige ADMINISTRATOR."""

from fastapi import APIRouter, Depends

from chatbot.adapters.inbound.http.auth.guards import require_roles
from chatbot.application.ports.token_verifier import Role
from chatbot.application.support_ticket import ListSupportTickets
from chatbot.domain.support_ticket import SupportTicket

_ADMIN = [Depends(require_roles(Role.ADMINISTRATOR))]


def _view(ticket: SupportTicket) -> dict[str, object]:
    return {
        "id": ticket.id,
        "actor": ticket.actor,
        "question": ticket.question,
        "view": ticket.view,
        "createdAt": ticket.created_at.isoformat(),
    }


def tickets_router(listing: ListSupportTickets) -> APIRouter:
    router = APIRouter(prefix="/admin/tickets", tags=["tickets"])

    @router.get("", dependencies=_ADMIN)
    async def list_tickets() -> list[dict[str, object]]:
        return [_view(ticket) for ticket in await listing.execute()]

    return router
