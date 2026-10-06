"""Puerto para guardar y volver a cargar el modelo entrenado."""

from typing import Protocol

from chatbot.application.ports.intent_model import IntentModel


class PersistableModel(IntentModel, Protocol):
    def artifact(self) -> bytes: ...


class ModelTrainer(Protocol):
    def train(self, examples: tuple[tuple[str, str], ...]) -> PersistableModel: ...

    def load(self, artifact: bytes) -> IntentModel: ...
