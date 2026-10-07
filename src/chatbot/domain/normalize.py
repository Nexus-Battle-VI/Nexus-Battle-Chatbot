"""Normaliza una pregunta antes del clasificador.

Minusculas, espacios colapsados y sin signos. No corrige ortografia: los
n-gramas de caracteres ya absorben el error.
"""

import re

_MARKS = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize_question(text: str) -> str:
    lowered = text.strip().lower()
    without_marks = _MARKS.sub(" ", lowered)
    return _SPACES.sub(" ", without_marks).strip()
