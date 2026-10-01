from datetime import UTC, datetime


class SystemClock:
    """Reloj del sistema. La hora la fija siempre el servidor."""

    def now(self) -> datetime:
        return datetime.now(UTC)
