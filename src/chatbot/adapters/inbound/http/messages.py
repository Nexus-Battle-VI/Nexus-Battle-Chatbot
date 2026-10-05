"""Consulta del visitante o del jugador (HU-47.2).

Publica: el visitante no trae token. Si trae uno, se verifica. El cuerpo no
acepta un identificador de usuario.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from chatbot.adapters.inbound.http.auth.guards import read_bearer_token
from chatbot.adapters.inbound.http.auth.markers import public
from chatbot.application.answer import Answer, AnswerQuestion
from chatbot.application.ports.token_verifier import TokenVerificationError
from chatbot.domain.errors import InvalidKnowledgeEntryError
from chatbot.domain.knowledge_entry import question_view

router_builder_prefix = "/messages"


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    view: str | None = None


def _payload(answer: Answer) -> dict[str, object]:
    return {
        "answered": answer.answered,
        "intent": answer.intent,
        "language": answer.language,
        "confidence": answer.confidence,
        "answer": answer.answer,
        "kind": answer.kind,
        "suggestions": list(answer.suggestions),
        "view": answer.view,
    }


def messages_router(answer_question: AnswerQuestion) -> APIRouter:
    router = APIRouter(tags=["conversation"])

    @router.post("/messages")
    @public
    async def ask(body: AskBody, request: Request) -> dict[str, object]:
        settings = request.app.state.auth
        if settings.jwt_enabled:
            token = read_bearer_token(request.headers.get("authorization"))
            if token is not None:
                try:
                    request.state.identity = await settings.verifier.verify(token)
                except TokenVerificationError as error:
                    raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
        try:
            view = question_view(body.view)
        except InvalidKnowledgeEntryError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
        result = await answer_question.execute(body.text, view)
        return _payload(result)

    return router
