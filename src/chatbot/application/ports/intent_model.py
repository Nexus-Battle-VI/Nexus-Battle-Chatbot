"""Puerto del modelo de intencion. La aplicacion no importa scikit-learn."""

from typing import Protocol


class IntentModel(Protocol):
    def predict(self, text: str) -> tuple[str | None, float, tuple[str, ...]]:
        """Etiqueta, confianza y las siguientes etiquetas, de mayor a menor."""


class IntentModelFactory(Protocol):
    def train(self, examples: tuple[tuple[str, str], ...]) -> IntentModel: ...
