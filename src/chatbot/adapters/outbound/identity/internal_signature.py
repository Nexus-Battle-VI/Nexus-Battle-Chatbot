"""Firma HMAC-SHA256 del contrato interno entre servicios (`/api/internal/v1/...`).

Debe producir EXACTAMENTE la misma firma que `internal-signature.ts` de los
servicios NestJS: es lo unico que hace que las dos partes lleguen al mismo
resultado. Por eso `canonical_body` no usa `json.dumps` a secas: reproduce el
`JSON.stringify` de JavaScript, que formatea los numeros y ordena las claves de
otra manera. La conformidad se comprueba con vectores generados por la
implementacion TypeScript (`tests/fixtures/internal-signature-vectors.json`).

SE DUPLICA A PROPOSITO (ADR-001): un paquete comun de identidad acoplaria los
servicios. El precio es esta copia; el contrato que ambas partes respetan esta
descrito en los dos ficheros.
"""

import hashlib
import hmac
import json
import math
from dataclasses import dataclass
from datetime import datetime

INTERNAL_SERVICE_HEADER = "x-internal-service"
INTERNAL_TIMESTAMP_HEADER = "x-internal-timestamp"
INTERNAL_SIGNATURE_HEADER = "x-internal-signature"

# Ventana admitida entre el sello de la peticion y el reloj de quien verifica.
# Acota la reutilizacion de una firma interceptada.
INTERNAL_CLOCK_SKEW_MS = 30_000

# Por encima de 2^53 JavaScript ya no representa los enteros con exactitud: lo
# que firmo quien llama es el numero redondeado, no el que llega en el texto.
_MAX_SAFE_INTEGER = 2**53 - 1


@dataclass(frozen=True)
class CanonicalRequest:
    service: str
    method: str
    path: str
    timestamp: str
    body: object


def _js_number(value: float) -> str:
    """Reproduce `Number.prototype.toString` (ECMAScript, seccion Number::toString)."""
    if not math.isfinite(value):
        # `JSON.stringify(NaN)` y de los infinitos produce `null`.
        return "null"
    if value == 0:
        # Incluye -0: JavaScript lo serializa como `0`.
        return "0"

    sign = "-" if value < 0 else ""
    # `repr` da la representacion mas corta que reconstruye el mismo double,
    # que es tambien la que elige JavaScript. Solo cambia la forma de escribirla.
    mantissa, _, exp_text = repr(abs(value)).partition("e")
    exponent = int(exp_text) if exp_text else 0
    integer_part, _, fraction_part = mantissa.partition(".")
    digits = (integer_part + fraction_part).lstrip("0")
    leading_zeros = len(integer_part + fraction_part) - len(
        (integer_part + fraction_part).lstrip("0")
    )
    digits = digits.rstrip("0") or "0"
    # n: posicion del punto decimal respecto al primer digito significativo.
    n = len(integer_part) - leading_zeros + exponent
    k = len(digits)

    if k <= n <= 21:
        text = digits + "0" * (n - k)
    elif 0 < n <= 21:
        text = f"{digits[:n]}.{digits[n:]}"
    elif -6 < n <= 0:
        text = "0." + "0" * (-n) + digits
    else:
        exp = n - 1
        exp_sign = "+" if exp >= 0 else "-"
        head = digits[0] if k == 1 else f"{digits[0]}.{digits[1:]}"
        text = f"{head}e{exp_sign}{abs(exp)}"
    return sign + text


def _utf16_key(key: str) -> bytes:
    # JavaScript compara cadenas por unidades UTF-16; Python, por puntos de
    # codigo. Solo difieren con caracteres fuera del plano basico, pero difieren.
    return key.encode("utf-16-be", "surrogatepass")


def canonical_body(value: object) -> str:  # noqa: PLR0911 - un retorno por tipo JSON
    """Serializacion determinista del cuerpo, con las claves ordenadas."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if abs(value) <= _MAX_SAFE_INTEGER:
            return str(value)
        return _js_number(float(value))
    if isinstance(value, float):
        return _js_number(value)
    if isinstance(value, str):
        # `ensure_ascii=False` reproduce `JSON.stringify`: no escapa lo que no es
        # ASCII y escapa los controles con `\\u00xx` en minusculas.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list | tuple):
        return "[" + ",".join(canonical_body(item) for item in value) + "]"
    if isinstance(value, dict):
        entries = sorted(
            ((str(k), v) for k, v in value.items()),
            key=lambda item: _utf16_key(item[0]),
        )
        return (
            "{"
            + ",".join(
                f"{json.dumps(k, ensure_ascii=False)}:{canonical_body(v)}" for k, v in entries
            )
            + "}"
        )
    raise TypeError(f"Tipo no serializable en el contrato interno: {type(value).__name__}")


def canonical_string(request: CanonicalRequest) -> str:
    """Servicio, metodo, ruta, sello y resumen del cuerpo, uno por linea.

    Firmar mas que el cuerpo es el punto: interceptada una peticion, la firma no
    sirve para otra ruta ni otro metodo.
    """
    body_digest = hashlib.sha256(canonical_body(request.body).encode("utf-8")).hexdigest()
    return "\n".join(
        [request.service, request.method.upper(), request.path, request.timestamp, body_digest]
    )


def sign_internal_request(secret: str, request: CanonicalRequest) -> str:
    return hmac.new(
        secret.encode("utf-8"), canonical_string(request).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def signature_matches(expected: str, received: str | None) -> bool:
    """Comparacion en tiempo constante.

    Una comparacion normal tarda mas cuanto mas prefijo coincide, y esa
    diferencia es medible.
    """
    if received is None:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), received.encode("utf-8"))


def timestamp_within_window(timestamp: str, now: datetime, skew_ms: int) -> bool:
    """Cierto si el sello (milisegundos desde la epoca) cae dentro de la ventana."""
    text = timestamp.strip()
    try:
        # `Number('')` es 0 en JavaScript; se reproduce para no aceptar distinto.
        sent = float(text) if text else 0.0
    except ValueError:
        return False
    if not math.isfinite(sent):
        return False
    now_ms = now.timestamp() * 1000
    return abs(now_ms - sent) <= skew_ms
