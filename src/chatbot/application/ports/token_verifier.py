"""Puerto de verificacion del testimonio de identidad.

Este servicio no emite tokens ni custodia claves: solo comprueba que el
testimonio que acompana a la peticion lo firmo el proveedor de identidad y que
sigue siendo valido. Vease ADR-004.

Se duplica en cada servicio a proposito, igual que en los servicios NestJS
(`TokenVerifierPort.ts`). Un paquete comun de identidad acoplaria los
servicios: cualquier cambio obligaria a un despliegue coordinado.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Role(StrEnum):
    """Vocabulario de roles que el proveedor de identidad puede afirmar.

    Vive junto al puerto y NO en el dominio: la fuente de verdad de los roles es
    Account; esto es la forma en que llegan.
    """

    PLAYER = "PLAYER"
    MODERATOR = "MODERATOR"
    ADMINISTRATOR = "ADMINISTRATOR"
    # Rol raiz del sistema (HU-02, HU-39). Si no estuviera en el vocabulario, una
    # cuenta que solo lo tuviera recibiria 403 en toda ruta administrativa sin
    # nada que lo explicara: es el defecto que ya ocurrio en los servicios NestJS.
    SUPER_ADMINISTRATOR = "SUPER_ADMINISTRATOR"


ALL_ROLES: frozenset[Role] = frozenset(Role)


def is_role(value: str) -> bool:
    return value in Role._value2member_map_


@dataclass(frozen=True)
class VerifiedIdentity:
    """Identidad ya verificada.

    `subject` es el `sub` del proveedor: es estable, un correo no lo es. El
    correo solo esta presente si el proveedor lo declara verificado, y los
    grupos que no son roles conocidos se descartan.
    """

    subject: str
    email: str | None = None
    roles: frozenset[Role] = field(default_factory=frozenset)


class TokenVerificationError(Exception):
    """Fallo de verificacion.

    Deliberadamente sin detalle: el motivo exacto por el que un token no es
    valido es informacion util para quien lo esta falsificando.
    """

    def __init__(self, message: str = "El testimonio de identidad no es valido.") -> None:
        super().__init__(message)


class TokenVerifierPort(Protocol):
    async def verify(self, token: str) -> VerifiedIdentity: ...
