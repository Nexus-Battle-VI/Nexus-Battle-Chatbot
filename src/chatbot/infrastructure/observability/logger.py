"""Registro estructurado en JSON por linea, con el mismo formato que los servicios NestJS.

Es el unico punto del servicio autorizado para escribir en la salida estandar;
la regla se hace cumplir con `T20` de ruff (equivalente a `no-console`).
"""

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Protocol

LogValue = str | int | float | bool | None
LogContext = Mapping[str, LogValue]

_LEVEL_WEIGHT = {"debug": 10, "info": 20, "warn": 30, "error": 40}


class Logger(Protocol):
    def debug(self, message: str, context: LogContext | None = None) -> None: ...
    def info(self, message: str, context: LogContext | None = None) -> None: ...
    def warn(self, message: str, context: LogContext | None = None) -> None: ...
    def error(self, message: str, context: LogContext | None = None) -> None: ...


def _iso(moment: datetime) -> str:
    # Mismo formato que `Date.prototype.toISOString`: milisegundos y `Z`.
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + (
        f"{moment.microsecond // 1000:03d}Z"
    )


class JsonLogger:
    def __init__(
        self,
        *,
        level: str,
        service: str,
        version: str,
        sink: Callable[[str], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._threshold = _LEVEL_WEIGHT[level]
        self._service = service
        self._version = version
        # Sumidero inyectable: permite verificar la salida sin capturar la consola.
        self._sink = sink or (lambda line: print(line, flush=True))
        self._clock = clock or (lambda: datetime.now(UTC))

    def _emit(self, level: str, message: str, context: LogContext | None) -> None:
        if _LEVEL_WEIGHT[level] < self._threshold:
            return
        record: dict[str, LogValue] = {
            "timestamp": _iso(self._clock()),
            "level": level,
            "service": self._service,
            "version": self._version,
            "message": message,
        }
        # El contexto no puede sobrescribir los campos fijos: un `service` en el
        # contexto haria que el registro atribuyera la linea a otro servicio.
        record.update({k: v for k, v in (context or {}).items() if k not in record})
        self._sink(json.dumps(record, ensure_ascii=False, separators=(",", ":")))

    def debug(self, message: str, context: LogContext | None = None) -> None:
        self._emit("debug", message, context)

    def info(self, message: str, context: LogContext | None = None) -> None:
        self._emit("info", message, context)

    def warn(self, message: str, context: LogContext | None = None) -> None:
        self._emit("warn", message, context)

    def error(self, message: str, context: LogContext | None = None) -> None:
        self._emit("error", message, context)
