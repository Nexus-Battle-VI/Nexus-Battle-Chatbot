"""Reenvía el testimonio del jugador a los `/me` ya publicados."""

import asyncio
import json
from collections.abc import Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

PATHS = {
    "inventory": "/api/inventories/me/items",
    "missions": "/api/v1/missions/me/active",
    "auction": "/api/v1/auctions/me/owned",
    "notifications": "/api/v1/notifications/me/pending",
    "transactions": "/api/v1/auctions/me/transactions",
}


def _read(url: str, access_token: str) -> dict[str, object] | None:
    request = Request(  # noqa: S310
        url,
        headers={"authorization": f"Bearer {access_token}"},
    )
    try:
        with urlopen(request, timeout=3) as response:  # noqa: S310
            raw = response.read()
    except (URLError, TimeoutError, OSError):
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return None
    return {str(key): value for key, value in parsed.items()}


class HttpPlayerData:
    def __init__(self, bases: Mapping[str, str | None]) -> None:
        self._bases = bases

    async def fetch(self, source: str, access_token: str) -> dict[str, object] | None:
        if source == "tournament":
            return None
        base = self._bases.get(source)
        path = PATHS.get(source)
        if base is None or base == "" or path is None:
            return None
        return await asyncio.to_thread(_read, f"{base.rstrip('/')}{path}", access_token)
