"""Ticket de una consulta no resuelta. Guarda la pregunta ya redactada."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SupportTicket:
    id: str
    actor: str
    question: str
    view: str | None
    created_at: datetime
