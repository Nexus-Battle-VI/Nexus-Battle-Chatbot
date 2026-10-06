"""Lectura del `/me` del propio jugador. El testimonio se reenvía; no hay un id en el cuerpo."""

from typing import Protocol


class PlayerDataPort(Protocol):
    async def fetch(self, source: str, access_token: str) -> dict[str, object] | None: ...
