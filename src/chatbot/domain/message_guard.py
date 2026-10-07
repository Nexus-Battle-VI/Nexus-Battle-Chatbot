"""Controles del texto de la consulta (HU-47.3).

El mensaje se trata como texto. Una inyeccion o un insulto se rechazan.
Contraseñas y tarjetas se redactan antes de guardar el historial.
"""

import re
import unicodedata

from chatbot.domain.errors import DomainError

_OFFENSIVE = (
    "hijueputa",
    "hijoeputa",
    "hijodeputa",
    "jueputa",
    "hpta",
    "malparido",
    "malparida",
    "gonorrea",
    "pirobo",
    "piroba",
    "guevon",
    "huevon",
    "puta",
    "puto",
    "marica",
    "maricon",
    "mierda",
    "pendejo",
    "cabron",
)
_INJECTION = re.compile(
    r"(<\s*script|javascript\s*:|union\s+select|;\s*drop\s+|\$\{|\.\./|\x00)",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"(?i)\b(contrasena|contraseña|password|clave|passwd)\b\s*[:=]\s*\S+"
    r"|\b(?:\d[ -]*?){13,19}\b"
)


class InjectionAttemptError(DomainError):
    """El texto parece codigo o una consulta, no una pregunta."""


class InappropriateContentError(DomainError):
    """El texto trae un insulto. Se rechaza el mensaje entero."""


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return without_marks.lower()


def assert_acceptable(text: str) -> None:
    if _INJECTION.search(text) is not None:
        raise InjectionAttemptError("La consulta no puede interpretarse como codigo.")
    plain = _plain(text)
    for term in _OFFENSIVE:
        if re.search(rf"\b{re.escape(term)}\b", plain) is not None:
            raise InappropriateContentError("La consulta tiene contenido no admitido.")


def redact_sensitive(text: str) -> str:
    return _SECRET.sub("[redactado]", text)
