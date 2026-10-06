"""Resúmenes de los `/me` que ya existen. No inventa campos que no vinieron."""

from collections.abc import Mapping


def summarize_inventory(payload: Mapping[str, object]) -> str | None:
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    total = payload.get("totalItems")
    count = total if isinstance(total, int) and not isinstance(total, bool) else len(items)
    if count == 0:
        return "No tienes objetos en el inventario."
    noun = "objeto" if count == 1 else "objetos"
    names: list[str] = []
    for item in items[:5]:
        if not isinstance(item, Mapping):
            continue
        product = item.get("product")
        name = product.get("name") if isinstance(product, Mapping) else None
        quantity = item.get("quantity")
        if isinstance(name, str) and isinstance(quantity, int) and not isinstance(quantity, bool):
            names.append(f"{name} x {quantity}")
    if len(names) == 0:
        return f"El inventario tiene {count} {noun}."
    return f"El inventario tiene {count} {noun}. En esta página: {', '.join(names)}."


def summarize_missions(payload: Mapping[str, object]) -> str | None:
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    if len(items) == 0:
        return "No tienes misiones en curso."
    parts: list[str] = []
    for item in items[:5]:
        if not isinstance(item, Mapping):
            continue
        name = item.get("missionName")
        progress = item.get("progressPercent")
        if isinstance(name, str) and isinstance(progress, int) and not isinstance(progress, bool):
            parts.append(f"{name} ({progress}%)")
    if len(parts) == 0:
        return f"Tienes {len(items)} misiones en curso."
    return f"Tienes {len(items)} misiones en curso: {', '.join(parts)}."


def summarize_auctions(payload: Mapping[str, object]) -> str | None:
    items = payload.get("items")
    total = payload.get("total")
    if not isinstance(items, list) or not isinstance(total, int) or isinstance(total, bool):
        return None
    if total == 0:
        return "No tienes subastas publicadas."
    states: list[str] = []
    for item in items[:5]:
        if isinstance(item, Mapping) and isinstance(item.get("status"), str):
            states.append(str(item.get("status")))
    if len(states) == 0:
        return f"Tienes {total} subastas."
    return f"Tienes {total} subastas. Estados en esta página: {', '.join(states)}."


def summarize_notifications(payload: Mapping[str, object]) -> str | None:
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    if len(items) == 0:
        return "No tienes notificaciones pendientes."
    return f"Tienes {len(items)} notificaciones pendientes."


def summarize_transactions(payload: Mapping[str, object]) -> str | None:
    items = payload.get("items")
    total = payload.get("total")
    if not isinstance(items, list) or not isinstance(total, int) or isinstance(total, bool):
        return None
    if total == 0:
        return "No tienes transacciones de subasta recientes."
    kinds: list[str] = []
    for item in items[:5]:
        if isinstance(item, Mapping) and isinstance(item.get("type"), str):
            kinds.append(str(item.get("type")))
    if len(kinds) == 0:
        return f"Tienes {total} transacciones de subasta."
    return f"Tienes {total} transacciones de subasta. En esta página: {', '.join(kinds)}."
