"""Valoración de una respuesta y preferencia de la hora (HU-51)."""

from fastapi import APIRouter, Query, Request

from chatbot.adapters.inbound.http.auth.markers import public
from chatbot.adapters.inbound.http.messages import (
    PreferenceBody,
    RatingBody,
    _actor,
    _identity,
    _rating_response,
)
from chatbot.application.conversation import ConversationSession
from chatbot.application.ports.model_version_repository import ModelVersionRepository


def feedback_router(session: ConversationSession, versions: ModelVersionRepository) -> APIRouter:
    router = APIRouter(tags=["conversation"])

    @router.post("/messages/{turn_id}/rating")
    @public
    async def rate(turn_id: str, body: RatingBody, request: Request) -> dict[str, object]:
        identity = await _identity(request)
        actor, _visitor_id = await _actor(identity, session, body.session_id)
        outcome = await session.rate(actor, turn_id, body.useful)
        return await _rating_response(outcome, turn_id, body.useful, versions)

    @router.get("/preferences")
    @public
    async def read_preferences(
        request: Request,
        session_id: str | None = Query(default=None, alias="sessionId"),
    ) -> dict[str, object]:
        identity = await _identity(request)
        actor, visitor_id = await _actor(identity, session, session_id)
        return {"sessionId": visitor_id, "showTime": await session.show_time(actor)}

    @router.put("/preferences")
    @public
    async def write_preferences(body: PreferenceBody, request: Request) -> dict[str, object]:
        identity = await _identity(request)
        actor, visitor_id = await _actor(identity, session, body.session_id)
        await session.set_show_time(actor, body.show_time)
        return {"sessionId": visitor_id, "showTime": body.show_time}

    return router
