"""Consulta del visitante o del jugador (HU-47.2 y HU-47.3).

Publica: el visitante no trae token. Si trae uno, se verifica. El cuerpo no
acepta un identificador de usuario. Antes de responder se aplican el limite,
la inyeccion y el filtro.
"""

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from chatbot.adapters.inbound.http.auth.guards import read_bearer_token
from chatbot.adapters.inbound.http.auth.markers import public
from chatbot.application.answer import Answer
from chatbot.application.conversation import ConversationSession, RateLimitExceededError
from chatbot.application.ports.token_verifier import TokenVerificationError, VerifiedIdentity
from chatbot.application.support_ticket import OpenSupportTicket
from chatbot.domain.errors import InvalidKnowledgeEntryError
from chatbot.domain.knowledge_entry import question_view
from chatbot.domain.message_guard import (
    InappropriateContentError,
    InjectionAttemptError,
    assert_acceptable,
    redact_sensitive,
)


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    text: str = Field(min_length=1, max_length=500)
    view: str | None = None
    session_id: str | None = Field(default=None, alias="sessionId")


def _payload(
    answer: Answer, session_id: str | None, ticket_id: str | None = None
) -> dict[str, object]:
    return {
        "answered": answer.answered,
        "intent": answer.intent,
        "language": answer.language,
        "confidence": answer.confidence,
        "answer": answer.answer,
        "kind": answer.kind,
        "suggestions": list(answer.suggestions),
        "view": answer.view,
        "sessionId": session_id,
        "modelVersion": answer.model_version,
        "assistedAction": _assisted(answer),
        "ticketId": ticket_id,
    }


def _assisted(answer: Answer) -> dict[str, str] | None:
    if answer.assisted_action is None:
        return None
    name, path = answer.assisted_action
    return {"name": name, "path": path}


async def _identity(request: Request) -> VerifiedIdentity | None:
    settings = request.app.state.auth
    if not settings.jwt_enabled:
        identity: VerifiedIdentity | None = getattr(request.state, "identity", None)
        return identity
    token = read_bearer_token(request.headers.get("authorization"))
    if token is None:
        return None
    try:
        verified: VerifiedIdentity = await settings.verifier.verify(token)
    except TokenVerificationError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    request.state.identity = verified
    return verified


def _actor(
    identity: VerifiedIdentity | None,
    session: ConversationSession,
    session_id: str | None,
) -> tuple[str, str | None]:
    if identity is not None and identity.subject != "anonymous":
        return f"player:{identity.subject}", None
    visitor = session.open_visitor_session(session_id)
    return f"visitor:{visitor}", visitor


def _reject(error: Exception) -> HTTPException:
    if isinstance(error, RateLimitExceededError):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error))
    if isinstance(error, (InjectionAttemptError, InappropriateContentError)):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(error))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(error))


def messages_router(session: ConversationSession, tickets: OpenSupportTicket) -> APIRouter:
    router = APIRouter(tags=["conversation"])

    @router.post("/messages")
    @public
    async def ask(body: AskBody, request: Request) -> dict[str, object]:
        identity = await _identity(request)
        ticket_id = None
        try:
            view = question_view(body.view)
            actor, visitor_id = _actor(identity, session, body.session_id)
            token = read_bearer_token(request.headers.get("authorization"))
            forwarded = token if identity is not None and identity.subject != "anonymous" else None
            answer = await session.ask(actor, body.text, view, forwarded)
            ticket_id = None
            if not answer.answered:
                opened = await tickets.execute(actor, redact_sensitive(body.text), view)
                ticket_id = opened.id
        except (RateLimitExceededError, InjectionAttemptError, InappropriateContentError) as error:
            raise _reject(error) from error
        except InvalidKnowledgeEntryError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
        return _payload(answer, visitor_id, ticket_id)

    @router.post("/tickets")
    @public
    async def open_ticket(body: AskBody, request: Request) -> dict[str, object]:
        identity = await _identity(request)
        try:
            view = question_view(body.view)
            actor, visitor_id = _actor(identity, session, body.session_id)
            session.allow(actor)
            assert_acceptable(body.text)
            opened = await tickets.execute(actor, redact_sensitive(body.text), view)
        except (RateLimitExceededError, InjectionAttemptError, InappropriateContentError) as error:
            raise _reject(error) from error
        except InvalidKnowledgeEntryError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
        return {"id": opened.id, "sessionId": visitor_id}

    @router.get("/messages/history")
    @public
    async def history(
        request: Request,
        session_id: str | None = Query(default=None, alias="sessionId"),
    ) -> dict[str, object]:
        identity = await _identity(request)
        actor, visitor_id = _actor(identity, session, session_id)
        turns = [
            {
                "question": turn.question,
                "answer": turn.answer,
                "modelVersion": turn.model_version,
            }
            for turn in session.history(actor)
        ]
        return {"sessionId": visitor_id, "turns": turns}

    @router.delete("/messages/history", status_code=status.HTTP_204_NO_CONTENT)
    @public
    async def clear(
        request: Request,
        session_id: str | None = Query(default=None, alias="sessionId"),
    ) -> None:
        identity = await _identity(request)
        actor, _visitor_id = _actor(identity, session, session_id)
        session.clear(actor)

    return router
