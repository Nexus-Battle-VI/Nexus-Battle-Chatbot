"""Reparto estable de la prueba A/B (HU-54.3).

El porcentaje lo decide el Product Owner. Cero significa que nadie ve a la
candidata.
"""

import hashlib


def sees_candidate(actor: str, percent: int) -> bool:
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    bucket = int.from_bytes(hashlib.sha256(actor.encode()).digest()[:8], "big") % 100
    return bucket < percent


def live_precision(useful: int, not_useful: int) -> float | None:
    """Útil / (útil + no útil). Sin valorar no entra. Sin valoraciones no hay cociente."""
    total = useful + not_useful
    if total == 0:
        return None
    return useful / total
