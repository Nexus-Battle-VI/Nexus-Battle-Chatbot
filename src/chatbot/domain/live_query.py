"""Intenciones que leen el `/me` del jugador. El torneo todavía no tiene esa ruta."""

LIVE_SOURCES = {
    "mi_inventario": "inventory",
    "mi_mision": "missions",
    "mi_subasta": "auction",
    "mi_notificacion": "notifications",
    "mi_transaccion": "transactions",
    "mi_torneo": "tournament",
}

SIGN_IN = "Inicia sesión para consultar tus datos."
UNAVAILABLE = "No pude consultar ese dato ahora."


def live_source(label: str | None) -> str | None:
    if label is None:
        return None
    language, separator, intent = label.partition(":")
    if separator == "" or language not in {"es", "en"}:
        return None
    return LIVE_SOURCES.get(intent)
