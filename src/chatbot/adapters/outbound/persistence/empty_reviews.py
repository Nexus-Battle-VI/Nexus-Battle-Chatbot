"""Hasta HU-51 no hay conversaciones revisadas que aportar al entrenamiento."""

from chatbot.domain.training_set import ConversationTurn


class EmptyReviewedConversations:
    async def list_reviewed(self) -> tuple[ConversationTurn, ...]:
        return ()
