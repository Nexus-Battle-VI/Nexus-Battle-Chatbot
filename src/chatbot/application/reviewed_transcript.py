"""Conversaciones ya valoradas, listas para el conjunto de entrenamiento (HU-51)."""

from chatbot.application.conversation import TextCipherPort
from chatbot.application.ports.transcript_repository import TranscriptRepository
from chatbot.domain.training_set import ConversationTurn


class ReviewedTranscript:
    def __init__(self, transcripts: TranscriptRepository, cipher: TextCipherPort) -> None:
        self._transcripts = transcripts
        self._cipher = cipher

    async def list_reviewed(self) -> tuple[ConversationTurn, ...]:
        reviewed: list[ConversationTurn] = []
        for turn in await self._transcripts.list_rated():
            reviewed.append(
                ConversationTurn(
                    text=self._cipher.decrypt(turn.question),
                    language=turn.language or "",
                    intent=turn.intent,
                    useful=turn.useful,
                    deleted=False,
                )
            )
        return tuple(reviewed)
