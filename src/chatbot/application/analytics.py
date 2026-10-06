"""Lee los agregados de uso a partir del historial y los tickets (HU-52)."""

from datetime import datetime

from chatbot.application.conversation import TextCipherPort
from chatbot.application.ports.support_ticket_repository import SupportTicketRepository
from chatbot.application.ports.transcript_repository import TranscriptRepository
from chatbot.domain.analytics import ObservedQuery, UsageReport, summarize


class ReadUsageAnalytics:
    def __init__(
        self,
        transcripts: TranscriptRepository,
        tickets: SupportTicketRepository,
        cipher: TextCipherPort,
    ) -> None:
        self._transcripts = transcripts
        self._tickets = tickets
        self._cipher = cipher

    async def execute(self, start: datetime, end: datetime) -> UsageReport:
        stored = await self._transcripts.list_between(start, end)
        queries = tuple(
            ObservedQuery(
                text=self._cipher.decrypt(turn.question),
                answered=turn.answer is not None,
                intent=turn.intent,
                useful=turn.useful,
                duration_ms=turn.duration_ms,
                created_at=turn.created_at,
            )
            for turn in stored
        )
        started = await self._transcripts.count_started(start, end)
        escalations = await self._tickets.count_between(start, end)
        return summarize(queries, started, escalations, start, end)
