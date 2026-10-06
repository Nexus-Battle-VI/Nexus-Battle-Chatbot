"""Conversaciones que HU-51 podrá aportar. Hoy el adaptador vacío no devuelve ninguna."""

from typing import Protocol

from chatbot.domain.training_set import ConversationTurn


class ReviewedConversationPort(Protocol):
    async def list_reviewed(self) -> tuple[ConversationTurn, ...]: ...
