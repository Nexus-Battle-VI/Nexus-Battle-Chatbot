"""Puerto de reloj.

La hora la fija siempre el servidor (ADR-019). Inyectarla como puerto permite
probar ventanas de tiempo sin dormir ni depender del reloj de la maquina.
"""

from datetime import datetime
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime: ...
