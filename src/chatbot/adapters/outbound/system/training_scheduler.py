"""Dispara el reentrenamiento dentro del proceso. Apagado salvo configuracion (ADR-019)."""

import asyncio
from contextlib import suppress

from chatbot.application.train_model import RetrainModel
from chatbot.infrastructure.observability.logger import Logger


class TrainingScheduler:
    def __init__(self, retrain: RetrainModel, interval_seconds: int, logger: Logger) -> None:
        self._retrain = retrain
        self._interval = interval_seconds
        self._logger = logger
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def run_once(self) -> None:
        try:
            outcome = await self._retrain.execute()
        except Exception as error:
            self._logger.error("model_retrain_failed", {"detail": str(error)})
            return
        self._logger.info(
            "model_retrain_finished",
            {
                "started": outcome.started,
                "promoted": outcome.promoted,
                "versionId": outcome.version_id,
                "accuracy": outcome.accuracy,
            },
        )

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self.run_once()
